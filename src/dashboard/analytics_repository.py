"""Read-only, parameterized queries for the warehouse analytics UI.

All metrics here count valid pickups from the sparse demand mart. SQL fragments
for OLAP grouping come only from the fixed allowlists below; user selections
are bound as query parameters.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date

import psycopg
from psycopg.rows import dict_row

from taxi_dw.db import open_connection


TIME_LEVELS = {
    "all": (),
    "month": ("date_trunc('month', demand_date)::date AS demand_month",),
    "day": ("demand_date",),
    "hour": ("demand_hour",),
    "day_hour": ("demand_date", "demand_hour"),
}
GEO_LEVELS = {
    "all": (),
    "borough": ("borough",),
    "zone": ("borough", "pickup_location_id", "zone_name"),
}
MAX_OLAP_ROWS = 5_000


class AnalyticsRepository:
    """Query the published mart without depending on RAW or staging."""

    def __init__(self, connection: psycopg.Connection | None = None):
        self._shared_connection = connection

    @contextmanager
    def _connection(self) -> Iterator[psycopg.Connection]:
        if self._shared_connection is not None:
            yield self._shared_connection
        else:
            with open_connection() as connection:
                yield connection

    def date_bounds(self) -> tuple[date | None, date | None]:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT min(coverage_start_date), max(coverage_end_date) "
                "FROM mart.mart_demand_coverage"
            ).fetchone()
        return row[0], row[1]

    def boroughs(self) -> list[str]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT DISTINCT borough FROM mart.mart_zone_hour_demand "
                "ORDER BY borough"
            ).fetchall()
        return [row[0] for row in rows]

    def available_months(self) -> list[date]:
        """Only source months reconciled across ingestion, fact, and mart."""
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT coverage_start_date FROM mart.mart_demand_coverage "
                "ORDER BY coverage_start_date"
            ).fetchall()
        return [row[0] for row in rows]

    def zones(self) -> list[dict]:
        with self._connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    "SELECT DISTINCT pickup_location_id, borough, zone_name "
                    "FROM mart.mart_zone_hour_demand "
                    "ORDER BY borough, zone_name, pickup_location_id"
                )
                return list(cursor.fetchall())

    def summary(
        self,
        start_date: date,
        end_date: date,
        *,
        borough: str | None = None,
        hour_range: tuple[int, int] = (0, 23),
        zone_ids: tuple[int, ...] = (),
    ) -> dict:
        where, parameters = self._filters(
            start_date, end_date, borough, hour_range, zone_ids
        )
        with self._connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    "SELECT coalesce(sum(trip_count), 0)::bigint AS trip_count, "
                    "count(DISTINCT pickup_location_id)::integer AS active_zones, "
                    "count(DISTINCT demand_date)::integer AS active_days "
                    "FROM mart.mart_zone_hour_demand WHERE " + where,
                    parameters,
                )
                return dict(cursor.fetchone())

    def olap(
        self,
        start_date: date,
        end_date: date,
        *,
        time_level: str,
        geo_level: str,
        borough: str | None = None,
        hour_range: tuple[int, int] = (0, 23),
        zone_ids: tuple[int, ...] = (),
        limit: int = MAX_OLAP_ROWS,
    ) -> tuple[list[dict], bool]:
        """Return grouped pickup counts and whether the row cap was reached."""

        if time_level not in TIME_LEVELS or geo_level not in GEO_LEVELS:
            raise ValueError("Unsupported OLAP grouping level")
        if (
            not isinstance(limit, int)
            or isinstance(limit, bool)
            or not 1 <= limit <= MAX_OLAP_ROWS
        ):
            raise ValueError(f"limit must be between 1 and {MAX_OLAP_ROWS}")

        where, parameters = self._filters(
            start_date, end_date, borough, hour_range, zone_ids
        )
        dimensions = (*TIME_LEVELS[time_level], *GEO_LEVELS[geo_level])
        select_columns = ", ".join(dimensions)
        prefix = f"{select_columns}, " if dimensions else ""
        grouping = (
            " GROUP BY " + ", ".join(str(i) for i in range(1, len(dimensions) + 1))
            if dimensions
            else ""
        )
        order = (
            " ORDER BY " + ", ".join(str(i) for i in range(1, len(dimensions) + 1))
            if time_level != "all" and dimensions
            else " ORDER BY trip_count DESC"
        )
        query = (
            f"SELECT {prefix}coalesce(sum(trip_count), 0)::bigint AS trip_count "
            "FROM mart.mart_zone_hour_demand WHERE "
            + where
            + grouping
            + order
            + " LIMIT %s"
        )
        with self._connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(query, (*parameters, limit + 1))
                rows = list(cursor.fetchall())
        return rows[:limit], len(rows) > limit

    @staticmethod
    def _filters(
        start_date: date,
        end_date: date,
        borough: str | None,
        hour_range: tuple[int, int],
        zone_ids: tuple[int, ...],
    ) -> tuple[str, tuple]:
        if not isinstance(start_date, date) or not isinstance(end_date, date):
            raise ValueError("A valid start and end date are required")
        if start_date > end_date:
            raise ValueError("The start date must not be after the end date")
        if (
            len(hour_range) != 2
            or not all(
                isinstance(hour, int) and not isinstance(hour, bool)
                for hour in hour_range
            )
            or not 0 <= hour_range[0] <= hour_range[1] <= 23
        ):
            raise ValueError("Hours must be within 0–23 in ascending order")
        if any(
            not isinstance(zone, int) or isinstance(zone, bool) or zone < 1
            for zone in zone_ids
        ):
            raise ValueError("Zone IDs must be positive integers")

        clauses = ["demand_date BETWEEN %s AND %s", "demand_hour BETWEEN %s AND %s"]
        parameters: list = [start_date, end_date, *hour_range]
        if borough is not None:
            clauses.append("borough = %s")
            parameters.append(borough)
        if zone_ids:
            clauses.append("pickup_location_id = ANY(%s::integer[])")
            parameters.append(list(zone_ids))
        return " AND ".join(clauses), tuple(parameters)
