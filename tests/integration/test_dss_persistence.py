"""PostgreSQL integration coverage for atomic Gate C persistence."""

from __future__ import annotations

from datetime import date
import os
import unittest
from uuid import UUID

import pandas as pd
import psycopg

from dss.persistence import ForecastRepository, ModelRunMetadata
from taxi_dw.config import DatabaseSettings


@unittest.skipUnless(
    os.environ.get("RUN_DB_TESTS") == "1",
    "set RUN_DB_TESTS=1 to run PostgreSQL integration tests",
)
class DssPersistenceIntegrationTests(unittest.TestCase):
    def test_atomic_run_round_trip_without_leaving_test_rows(self):
        settings = DatabaseSettings.from_environment()
        run_id = UUID("00000000-0000-0000-0000-000000000003")
        with psycopg.connect(**settings.as_connection_kwargs()) as connection:
            with connection.transaction(force_rollback=True):
                repository = ForecastRepository(connection)
                saved = repository.save_run(
                    ModelRunMetadata(
                        model_name="integration-baseline",
                        model_version="test",
                        feature_version="test",
                        recommendation_version="test",
                        train_start_date=date(2024, 1, 1),
                        train_end_date=date(2024, 1, 31),
                        validation_start_date=date(2024, 2, 1),
                        validation_end_date=date(2024, 2, 15),
                        metrics={"validation": {"wape": 0.25}},
                        git_commit_sha="integration-test",
                    ),
                    self._forecast_rows(),
                    run_id=run_id,
                )
                self.assertEqual(saved, run_id)
                latest = repository.latest_run(date(2024, 4, 1))
                self.assertIsNotNone(latest)
                self.assertEqual(latest["run_id"], run_id)
                rows = repository.read_forecasts(
                    run_id, forecast_date=date(2024, 4, 1)
                )
                self.assertEqual(len(rows), 24)
                self.assertEqual(rows["predicted_trip_count"].sum(), 48.0)

        with psycopg.connect(**settings.as_connection_kwargs()) as connection:
            count = connection.execute(
                "SELECT count(*) FROM dss.model_run WHERE run_id = %s", (run_id,)
            ).fetchone()[0]
        self.assertEqual(count, 0)

    @staticmethod
    def _forecast_rows() -> pd.DataFrame:
        return pd.DataFrame(
            {
                "forecast_date": [date(2024, 4, 1)] * 24,
                "demand_hour": list(range(24)),
                "pickup_zone_key": ["integration-zone-1"] * 24,
                "pickup_location_id": [1] * 24,
                "borough": ["Manhattan"] * 24,
                "zone_name": ["Integration Zone"] * 24,
                "predicted_trip_count": [2.0] * 24,
                "baseline_trip_count": [1.0] * 24,
                "historical_p50": [1.0] * 24,
                "historical_p75": [2.0] * 24,
                "demand_ratio": [2.0] * 24,
                "demand_level": ["High"] * 24,
                "recommendation": ["Integration recommendation"] * 24,
                "recommendation_reason": ["Integration reason"] * 24,
                "is_actionable": [True] * 24,
            }
        )


if __name__ == "__main__":
    unittest.main()
