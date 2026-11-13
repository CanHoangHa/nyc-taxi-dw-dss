"""DSS service filtering and latest-run tests."""

from __future__ import annotations

from datetime import date
import unittest
from uuid import UUID

import pandas as pd

from dss.service import DssService


class FakeRepository:
    run_id = UUID("00000000-0000-0000-0000-000000000001")

    def available_forecast_dates(self):
        return [date(2024, 4, 1)]

    def latest_run(self, forecast_date=None):
        if forecast_date == date(2024, 4, 2):
            return None
        return {
            "run_id": self.run_id,
            "metrics_json": {"validation": {"wape": 0.2}},
        }

    def read_forecasts(self, run_id, forecast_date=None):
        assert run_id == self.run_id
        return pd.DataFrame(
            {
                "forecast_date": [forecast_date] * 3,
                "borough": ["Queens", "Manhattan", "Queens"],
                "pickup_location_id": [2, 1, 2],
                "demand_hour": [9, 8, 8],
                "demand_level": ["Medium", "High", "High"],
                "predicted_trip_count": [5.0, 7.0, 6.0],
            }
        )


class DssServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = DssService(FakeRepository())

    def test_ranks_level_then_prediction(self):
        rows = self.service.ranked_recommendations(date(2024, 4, 1))
        self.assertEqual(rows["predicted_trip_count"].tolist(), [7.0, 6.0, 5.0])

    def test_filters_borough_hour_and_zone(self):
        rows = self.service.ranked_recommendations(
            date(2024, 4, 1), borough="Queens", hour_range=(8, 8), zone_ids=(2,)
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.loc[0, "predicted_trip_count"], 6.0)

    def test_missing_forecast_is_empty(self):
        rows = self.service.ranked_recommendations(date(2024, 4, 2))
        self.assertTrue(rows.empty)

    def test_exposes_versioned_run_metrics(self):
        metrics = self.service.model_metrics(date(2024, 4, 1))
        self.assertEqual(metrics["validation"]["wape"], 0.2)

    def test_snapshot_keeps_metadata_metrics_and_rows_on_one_run(self):
        from unittest.mock import patch
        repository = FakeRepository()
        with patch.object(repository, "latest_run", wraps=repository.latest_run) as latest:
            run, rows, metrics = DssService(repository).forecast_snapshot(date(2024, 4, 1))
        self.assertEqual(latest.call_count, 1)
        self.assertEqual(run["run_id"], repository.run_id)
        self.assertEqual(len(rows), 3)
        self.assertEqual(metrics["validation"]["wape"], 0.2)


if __name__ == "__main__":
    unittest.main()
