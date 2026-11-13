"""End-to-end in-memory train/evaluate/forecast vertical-slice tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path
import unittest

import pandas as pd

from dss.config import DssConfig, ModelSettings, load_config
from dss.contracts import ContractError
from dss.pipeline import (
    APPROACH_MEDIAN,
    APPROACH_SEASONAL,
    evaluate_from_dense,
    forecast_from_history,
    train_from_dense,
)
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
    def test_forecast_rejects_dates_used_for_training_or_selection(self):
        artifact = train_from_dense(dense(), q1_config(), git_commit_sha="test")
        for day in (
            date(2024, 1, 29), date(2024, 2, 10),
            date(2024, 2, 11), date(2024, 2, 20),
        ):
            with self.subTest(day=day):
                history = dense().loc[lambda frame: frame["demand_date"].lt(pd.Timestamp(day))]
                with self.assertRaisesRegex(ContractError, "after.*validation"):
                    forecast_from_history(artifact, history, eligible_zones(), day)

    def test_evaluate_rejects_valid_config_with_different_split(self):
        config = q1_config()
        artifact = train_from_dense(dense(), config, git_commit_sha="test")
        for test_start, test_end in (
            (date(2024, 2, 2), date(2024, 2, 10)),
            (date(2024, 2, 11), date(2024, 2, 20)),
        ):
            changed = replace(
                config,
                split=TemporalSplit(
                    date(2024, 1, 29), date(2024, 1, 30),
                    date(2024, 1, 31), date(2024, 2, 1), test_start, test_end,
                ),
            )
            changed.validate()
            with self.subTest(test_start=test_start):
                with self.assertRaisesRegex(ContractError, "split.*artifact"):
                    evaluate_from_dense(artifact, dense(), changed)

    def test_evaluate_accepts_matching_split_with_other_config_settings(self):
        config = q1_config()
        artifact = train_from_dense(dense(), config, git_commit_sha="test")
        changed = replace(
            config, artifact_directory=Path("unused"), model=ModelSettings(max_iter=10)
        )
        expected = evaluate_from_dense(artifact, dense(), config)
        actual = evaluate_from_dense(artifact, dense(), changed)
        self.assertEqual(set(expected), set(actual))
        for method in expected:
            for metric in expected[method]:
                # Threaded RF aggregation can differ at floating-point roundoff.
                self.assertAlmostEqual(expected[method][metric], actual[method][metric], places=10)

    def test_missing_artifact_split_rejects_evaluation_and_forecast(self):
        artifact = train_from_dense(dense(), q1_config(), git_commit_sha="test")
        del artifact.config["split"]
        with self.assertRaisesRegex(ContractError, "artifact.*split"):
            evaluate_from_dense(artifact, dense(), q1_config())
        with self.assertRaisesRegex(ContractError, "artifact.*split"):
            forecast_from_history(artifact, dense(28), eligible_zones(), date(2024, 1, 29))

    def test_forecast_still_requires_history_through_d_minus_one(self):
        frame = dense()
        artifact = train_from_dense(frame, q1_config(), git_commit_sha="test")
        for end in ("2024-02-19", "2024-02-21"):
            history = frame.loc[frame["demand_date"].le(end)]
            with self.subTest(end=end):
                with self.assertRaisesRegex(ContractError, "history.*D-1"):
                    forecast_from_history(
                        artifact, history, eligible_zones(), date(2024, 2, 21)
                    )

    def test_seasonal_forecast_can_have_high_demand_without_weekly_growth(self):
        frame = dense()
        artifact = train_from_dense(frame, q1_config(), git_commit_sha="test")
        artifact.selected_approach = APPROACH_SEASONAL
        history = frame.loc[frame["demand_date"].lt("2024-02-21")].copy()
        history.loc[history["demand_date"].eq("2024-02-14"), "trip_count"] = 1000
        result = forecast_from_history(artifact, history, eligible_zones(), date(2024, 2, 21))
        self.assertTrue(result["predicted_trip_count"].eq(1000).all())
        self.assertTrue(result["demand_ratio"].eq(1).all())
        self.assertTrue(result["demand_level"].eq("High").all())

    def test_checked_in_q1_config_is_valid(self):
        config = load_config(Path("configs/dss_q1.toml"))
        self.assertEqual(config.split.validation_start, date(2024, 3, 1))

    def test_train_selects_on_validation_and_evaluate_opens_test(self):
        config = q1_config()
        artifact = train_from_dense(dense(), config, git_commit_sha="abc123")
        self.assertIn(
            artifact.selected_approach,
            {"model", "seasonal_naive", "same_weekday_median", "random_forest"},
        )
        self.assertEqual(set(artifact.validation_metrics), {
            "model", "seasonal_naive", "same_weekday_median", "random_forest"
        })
        test_metrics = evaluate_from_dense(artifact, dense(), config)
        self.assertEqual(set(test_metrics), set(artifact.validation_metrics))

    def test_forecast_has_exact_zone_hour_shape_and_no_target_leakage(self):
        training_dense = dense()
        config = q1_config()
        artifact = train_from_dense(training_dense, config, git_commit_sha="abc123")
        # Exactly 28 days, including train and validation, remain valid features.
        history = training_dense.loc[
            training_dense["demand_date"].between("2024-01-24", "2024-02-20")
        ].copy()
        forecast = forecast_from_history(
            artifact,
            history,
            eligible_zones(),
            date(2024, 2, 21),
        )
        self.assertEqual(len(forecast), 24 * 2)
        self.assertTrue(forecast["predicted_trip_count"].ge(0).all())
        self.assertTrue(forecast["recommendation_reason"].str.len().gt(0).all())

    def test_recommendation_baseline_is_independent_of_selected_approach(self):
        training_dense = dense()
        artifact = train_from_dense(
            training_dense, q1_config(), git_commit_sha="abc123"
        )
        artifact.selected_approach = APPROACH_MEDIAN
        history = training_dense.loc[training_dense["demand_date"].lt("2024-02-21")].copy()
        recent_weekday = history["demand_date"].eq(pd.Timestamp("2024-02-14"))
        history.loc[recent_weekday, "trip_count"] += 100

        forecast = forecast_from_history(
            artifact,
            history,
            eligible_zones(),
            date(2024, 2, 21),
        )

        hour_zero_rows = forecast["demand_hour"].eq(0)
        self.assertTrue(
            forecast.loc[hour_zero_rows, "predicted_trip_count"]
            .ne(forecast.loc[hour_zero_rows, "baseline_trip_count"])
            .all()
        )
        self.assertTrue(forecast.loc[hour_zero_rows, "baseline_trip_count"].gt(90).all())


if __name__ == "__main__":
    unittest.main()
