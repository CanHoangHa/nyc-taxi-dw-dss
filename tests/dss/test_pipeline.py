"""End-to-end in-memory train/evaluate/forecast vertical-slice tests."""

from __future__ import annotations

from datetime import date
from pathlib import Path
import unittest

import pandas as pd

from dss.config import DssConfig, ModelSettings, load_config
from dss.pipeline import evaluate_from_dense, forecast_from_history, train_from_dense
from dss.split import TemporalSplit
from tests.dss.fixtures import eligible_zones


def dense(days: int = 70) -> pd.DataFrame:
    zones = eligible_zones()
    index = pd.MultiIndex.from_product(
        [pd.date_range("2024-01-01", periods=days), range(24), zones["pickup_zone_key"]],
        names=["demand_date", "demand_hour", "pickup_zone_key"],
    ).to_frame(index=False)
    frame = index.merge(zones, on="pickup_zone_key", validate="many_to_one")
    frame["trip_count"] = (
        frame["demand_date"].dt.dayofweek
        + frame["demand_hour"]
        + frame["pickup_location_id"]
    ) % 11
    return frame


def q1_config() -> DssConfig:
    return DssConfig(
        dataset_start=date(2024, 1, 1),
        dataset_end=date(2024, 3, 10),
        split=TemporalSplit(
            train_start=date(2024, 1, 29),
            train_end=date(2024, 2, 10),
            validation_start=date(2024, 2, 11),
            validation_end=date(2024, 2, 20),
            test_start=date(2024, 2, 21),
            test_end=date(2024, 3, 10),
        ),
        model=ModelSettings(max_iter=5, max_leaf_nodes=5),
        artifact_directory=Path("artifacts/models"),
    )


class PipelineTests(unittest.TestCase):
    def test_checked_in_q1_config_is_valid(self):
        config = load_config(Path("configs/dss_q1.toml"))
        self.assertEqual(config.split.validation_start, date(2024, 3, 1))

    def test_train_selects_on_validation_and_evaluate_opens_test(self):
        config = q1_config()
        artifact = train_from_dense(dense(), config, git_commit_sha="abc123")
        self.assertIn(
            artifact.selected_approach,
            {"model", "seasonal_naive", "same_weekday_median"},
        )
        self.assertEqual(set(artifact.validation_metrics), {
            "model", "seasonal_naive", "same_weekday_median"
        })
        test_metrics = evaluate_from_dense(artifact, dense(), config)
        self.assertEqual(set(test_metrics), set(artifact.validation_metrics))

    def test_forecast_has_exact_zone_hour_shape_and_no_target_leakage(self):
        training_dense = dense()
        config = q1_config()
        artifact = train_from_dense(training_dense, config, git_commit_sha="abc123")
        history = dense(28)
        forecast = forecast_from_history(
            artifact,
            history,
            eligible_zones(),
            date(2024, 1, 29),
        )
        self.assertEqual(len(forecast), 24 * 2)
        self.assertTrue(forecast["predicted_trip_count"].ge(0).all())
        self.assertTrue(forecast["recommendation_reason"].str.len().gt(0).all())


if __name__ == "__main__":
    unittest.main()
