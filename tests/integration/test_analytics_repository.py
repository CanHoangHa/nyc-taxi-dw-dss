"""End-to-end analytical invariants against a built local warehouse."""

from __future__ import annotations

import os
import unittest

from dashboard.analytics_repository import AnalyticsRepository
from taxi_dw.db import open_connection


@unittest.skipUnless(
    os.environ.get("RUN_ANALYTICS_TESTS") == "1",
    "set RUN_ANALYTICS_TESTS=1 after dbt run to test the analytics mart",
)
class AnalyticsRepositoryDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repository = AnalyticsRepository()
        cls.first_date, cls.last_date = cls.repository.date_bounds()
        if cls.first_date is None:
            raise unittest.SkipTest("No demand mart rows are available")

    def test_overview_and_rollups_match_fact_trips(self):
        repository = self.repository
        first, last = self.first_date, self.last_date
        overview = repository.summary(first, last)
        month_rows, truncated = repository.olap(
            first, last, time_level="month", geo_level="all"
        )
        borough_rows, borough_truncated = repository.olap(
            first, last, time_level="all", geo_level="borough"
        )
        with open_connection() as connection:
            fact_count = connection.execute(
                "SELECT count(*) FROM dw.fact_trip "
                "WHERE pickup_datetime::date BETWEEN %s AND %s",
                (first, last),
            ).fetchone()[0]
        self.assertFalse(truncated)
        self.assertFalse(borough_truncated)
        self.assertEqual(overview["trip_count"], fact_count)
        self.assertEqual(sum(row["trip_count"] for row in month_rows), fact_count)
        self.assertEqual(sum(row["trip_count"] for row in borough_rows), fact_count)

    def test_slice_and_dice_preserve_counts(self):
        repository = self.repository
        first, last = self.first_date, self.last_date
        selected_borough = repository.boroughs()[0]
        summary = repository.summary(first, last, borough=selected_borough)
        hourly, truncated = repository.olap(
            first,
            last,
            time_level="hour",
            geo_level="all",
            borough=selected_borough,
        )
        self.assertFalse(truncated)
        self.assertEqual(sum(row["trip_count"] for row in hourly), summary["trip_count"])

        selected_zone = repository.zones()[0]["pickup_location_id"]
        diced = repository.summary(first, last, hour_range=(17, 20), zone_ids=(selected_zone,))
        with open_connection() as connection:
            expected = connection.execute(
                "SELECT coalesce(sum(trip_count), 0) "
                "FROM mart.mart_zone_hour_demand "
                "WHERE demand_date BETWEEN %s AND %s "
                "AND demand_hour BETWEEN 17 AND 20 "
                "AND pickup_location_id = %s",
                (first, last, selected_zone),
            ).fetchone()[0]
        self.assertEqual(diced["trip_count"], expected)

    def test_coverage_months_match_reconciled_months(self):
        with open_connection() as connection:
            rows = connection.execute(
                "SELECT coverage_start_date, coverage_end_date, valid_trip_count "
                "FROM mart.mart_demand_coverage ORDER BY coverage_start_date"
            ).fetchall()
            mart_total = connection.execute(
                "SELECT coalesce(sum(trip_count), 0) FROM mart.mart_zone_hour_demand"
            ).fetchone()[0]
        self.assertEqual(self.repository.available_months(), [row[0] for row in rows])
        self.assertEqual(self.repository.date_bounds(), (rows[0][0], rows[-1][1]))
        self.assertEqual(sum(row[2] for row in rows), mart_total)


if __name__ == "__main__":
    unittest.main()
