"""Contract checks for the analytical query boundary."""

import unittest
from datetime import date

from dashboard.analytics_repository import AnalyticsRepository


class AnalyticsRepositoryValidationTests(unittest.TestCase):
    def test_rejects_unapproved_grouping_before_database_access(self):
        repository = AnalyticsRepository()
        with self.assertRaisesRegex(ValueError, "Unsupported OLAP"):
            repository.olap(
                date(2024, 1, 1),
                date(2024, 1, 31),
                time_level="day; DROP TABLE dw.fact_trip",
                geo_level="zone",
            )

    def test_rejects_reversed_dates_and_invalid_hours(self):
        repository = AnalyticsRepository()
        with self.assertRaisesRegex(ValueError, "start date"):
            repository.summary(date(2024, 2, 1), date(2024, 1, 31))
        with self.assertRaisesRegex(ValueError, "Hours"):
            repository.summary(
                date(2024, 1, 1), date(2024, 1, 31), hour_range=(18, 8)
            )


if __name__ == "__main__":
    unittest.main()
