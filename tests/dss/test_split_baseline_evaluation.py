"""Temporal split, baseline, and evaluation tests."""

from __future__ import annotations

import math
import unittest

import pandas as pd

from dss.baseline import add_baseline_predictions, predict_baseline
from dss.contracts import ContractError
from dss.evaluation import evaluate_predictions, regression_metrics
from dss.features import build_features, complete_feature_rows
from dss.split import TemporalSplit, split_by_date
from tests.dss.test_features import daily_series


class SplitBaselineEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.features = complete_feature_rows(build_features(daily_series(70)))

    def test_temporal_split_is_ordered_and_inclusive(self):
        parts = split_by_date(
            self.features,
            TemporalSplit(
                train_start=pd.Timestamp("2024-01-29"),
                train_end=pd.Timestamp("2024-02-10"),
                validation_start=pd.Timestamp("2024-02-11"),
                validation_end=pd.Timestamp("2024-02-20"),
                test_start=pd.Timestamp("2024-02-21"),
                test_end=pd.Timestamp("2024-03-05"),
            ),
        )
        self.assertLess(parts.train["demand_date"].max(), parts.validation["demand_date"].min())
        self.assertLess(parts.validation["demand_date"].max(), parts.test["demand_date"].min())

    def test_rejects_overlapping_split(self):
        with self.assertRaisesRegex(ContractError, "non-overlapping"):
            split_by_date(
                self.features,
                TemporalSplit(
                    train_start=pd.Timestamp("2024-01-29"),
                    train_end=pd.Timestamp("2024-02-11"),
                    validation_start=pd.Timestamp("2024-02-11"),
                    validation_end=pd.Timestamp("2024-02-20"),
                    test_start=pd.Timestamp("2024-02-21"),
                    test_end=pd.Timestamp("2024-03-05"),
                ),
            )

    def test_two_baselines_cover_complete_rows(self):
        predicted = add_baseline_predictions(self.features)
        self.assertFalse(predicted["prediction_seasonal_naive"].isna().any())
        self.assertFalse(predicted["prediction_same_weekday_median"].isna().any())

    def test_baseline_rejects_warmup_rows(self):
        incomplete = build_features(daily_series(10))
        with self.assertRaisesRegex(ContractError, "incomplete history"):
            predict_baseline(incomplete, "seasonal_naive")

    def test_metrics_handle_zero_actual_total(self):
        metrics = regression_metrics(pd.Series([0, 0]), pd.Series([0, 1]))
        self.assertEqual(metrics["mae"], 0.5)
        self.assertTrue(math.isnan(metrics["wape"]))

    def test_grouped_evaluation(self):
        frame = pd.DataFrame(
            {
                "borough": ["A", "A", "B"],
                "trip_count": [1, 3, 2],
                "prediction": [2, 3, 1],
            }
        )
        report = evaluate_predictions(
            frame, prediction_column="prediction", group_by=("borough",)
        )
        self.assertEqual(report["borough"].tolist(), ["A", "B"])
        self.assertEqual(report["row_count"].tolist(), [2.0, 1.0])


if __name__ == "__main__":
    unittest.main()
