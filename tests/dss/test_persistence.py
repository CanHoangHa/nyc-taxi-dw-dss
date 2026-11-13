"""Gate C output and transaction behavior tests."""

from __future__ import annotations

from datetime import date
import unittest
from uuid import UUID

import pandas as pd

from dss.contracts import ContractError
from dss.persistence import ForecastRepository, ModelRunMetadata, validate_forecasts


def forecast_rows(hours: int = 24) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "forecast_date": [date(2024, 4, 1)] * hours,
            "demand_hour": list(range(hours)),
            "pickup_zone_key": ["zone-1"] * hours,
            "pickup_location_id": [1] * hours,
            "borough": ["Manhattan"] * hours,
            "zone_name": ["Alpha"] * hours,
            "predicted_trip_count": [2.0] * hours,
            "baseline_trip_count": [1.0] * hours,
            "historical_p50": [1.0] * hours,
            "historical_p75": [2.0] * hours,
            "demand_ratio": [2.0] * hours,
            "demand_level": ["High"] * hours,
            "recommendation": ["Act"] * hours,
            "recommendation_reason": ["Reason"] * hours,
            "is_actionable": [True] * hours,
        }
    )


class FakeCursor:
    def __init__(self, fail_forecasts: bool = False):
        self.fail_forecasts = fail_forecasts
        self.execute_calls = []
        self.executemany_calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, query, parameters=()):
        self.execute_calls.append((query, parameters))

    def executemany(self, query, rows):
        materialized = list(rows)
        self.executemany_calls.append((query, materialized))
        if self.fail_forecasts:
            raise RuntimeError("insert failed")


class FakeTransaction:
    def __init__(self):
        self.committed = False
        self.rolled_back = False

    def __enter__(self):
        return self

    def __exit__(self, error_type, *_):
        self.committed = error_type is None
        self.rolled_back = error_type is not None
        return False


class FakeConnection:
    def __init__(self, fail_forecasts: bool = False):
        self.cursor_value = FakeCursor(fail_forecasts)
        self.transaction_value = FakeTransaction()

    def cursor(self, **_):
        return self.cursor_value

    def transaction(self):
        return self.transaction_value


class PersistenceTests(unittest.TestCase):
    def metadata(self):
        return ModelRunMetadata(
            model_name="candidate",
            model_version="1",
            feature_version="1",
            recommendation_version="1",
            train_start_date=date(2024, 1, 1),
            train_end_date=date(2024, 2, 15),
            validation_start_date=date(2024, 2, 16),
            validation_end_date=date(2024, 3, 15),
            metrics={"wape": 0.2},
            git_commit_sha="abc123",
        )

    def test_validates_rectangular_forecast(self):
        self.assertEqual(len(validate_forecasts(forecast_rows())), 24)
        with self.assertRaisesRegex(ContractError, "24 rows"):
            validate_forecasts(forecast_rows(23))

    def test_rejects_fractional_hour_before_database_insert(self):
        frame = forecast_rows()
        frame["demand_hour"] = frame["demand_hour"].astype("float64")
        frame.loc[0, "demand_hour"] = 0.5
        with self.assertRaisesRegex(ContractError, "0..23"):
            validate_forecasts(frame)

    def test_rejects_null_forecast_date_before_database_insert(self):
        frame = forecast_rows()
        frame.loc[0, "forecast_date"] = None
        with self.assertRaisesRegex(ContractError, "forecast_date"):
            validate_forecasts(frame)

    def test_run_and_rows_commit_together(self):
        connection = FakeConnection()
        run_id = ForecastRepository(connection).save_run(
            self.metadata(),
            forecast_rows(),
            run_id=UUID("00000000-0000-0000-0000-000000000001"),
        )
        self.assertEqual(str(run_id), "00000000-0000-0000-0000-000000000001")
        self.assertTrue(connection.transaction_value.committed)
        self.assertEqual(len(connection.cursor_value.executemany_calls[0][1]), 24)

    def test_forecast_failure_rolls_back_metadata(self):
        connection = FakeConnection(fail_forecasts=True)
        with self.assertRaisesRegex(RuntimeError, "insert failed"):
            ForecastRepository(connection).save_run(self.metadata(), forecast_rows())
        self.assertTrue(connection.transaction_value.rolled_back)
        self.assertFalse(connection.transaction_value.committed)


if __name__ == "__main__":
    unittest.main()
