"""Read-only warehouse queries for DSS dataset preparation."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date

import pandas as pd
import psycopg
from psycopg.rows import dict_row

from dss.contracts import (
    require_covered_range,
    validate_coverage,
    validate_sparse_demand,
    validate_zones,
)
from taxi_dw.db import open_connection


class DemandRepository:
    """Read Gate B interfaces without depending on RAW, staging, or fact tables."""

    def __init__(self, connection: psycopg.Connection | None = None):
        self._shared_connection = connection

    @contextmanager
    def _connection(self) -> Iterator[psycopg.Connection]:
        if self._shared_connection is not None:
            yield self._shared_connection
        else:
            with open_connection() as connection:
                yield connection

    def coverage(self) -> pd.DataFrame:
        with self._connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    "SELECT source_year, source_month, coverage_start_date, "
                    "coverage_end_date, valid_trip_count "
                    "FROM mart.mart_demand_coverage "
                    "ORDER BY coverage_start_date"
                )
                rows = list(cursor.fetchall())
        return validate_coverage(pd.DataFrame(rows))

    def eligible_zones(self) -> pd.DataFrame:
        with self._connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    "SELECT zone_key AS pickup_zone_key, "
                    "location_id AS pickup_location_id, borough, zone_name, "
                    "is_recommendation_eligible "
                    "FROM dw.dim_taxi_zone "
                    "WHERE is_recommendation_eligible "
                    "ORDER BY location_id"
                )
                rows = list(cursor.fetchall())
        return validate_zones(pd.DataFrame(rows))

    def sparse_demand(self, start_date: date, end_date: date) -> pd.DataFrame:
        coverage = self.coverage()
        require_covered_range(coverage, start_date, end_date)
        with self._connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    "SELECT demand_date, demand_hour, pickup_zone_key, "
                    "pickup_location_id, borough, zone_name, "
                    "is_recommendation_eligible, trip_count "
                    "FROM mart.mart_zone_hour_demand "
                    "WHERE demand_date BETWEEN %s AND %s "
                    "ORDER BY demand_date, demand_hour, pickup_zone_key",
                    (start_date, end_date),
                )
                rows = list(cursor.fetchall())
        return validate_sparse_demand(pd.DataFrame(rows))
