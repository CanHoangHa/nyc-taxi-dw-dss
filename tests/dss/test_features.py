"""Leakage and calendar-gap tests for demand features."""

from __future__ import annotations

import unittest

import pandas as pd

from dss.features import MODEL_FEATURES, build_features, complete_feature_rows


def daily_series(days: int = 42) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=days, freq="D")
    return pd.DataFrame(
        {
            "demand_date": dates,
            "demand_hour": 8,
            "pickup_zone_key": "zone-1",
            "pickup_location_id": 1,
            "borough": "Manhattan",
            "zone_name": "Alpha",
            "trip_count": range(days),
        }
    )


class FeatureTests(unittest.TestCase):
    def test_features_use_only_prior_dates(self):
        features = build_features(daily_series())
        row = features.loc[features["demand_date"] == pd.Timestamp("2024-01-29")].iloc[0]
        self.assertEqual(row["lag_1d"], 27)
        self.assertEqual(row["lag_7d"], 21)
        self.assertEqual(row["rolling_mean_7d"], 24)
        self.assertEqual(row["rolling_median_28d"], 13.5)
        self.assertEqual(row["same_weekday_median_4w"], 10.5)
        self.assertTrue(row["is_feature_complete"])

    def test_future_target_mutation_does_not_change_past_features(self):
        original = daily_series()
        mutated = original.copy()
        mutated.loc[mutated["demand_date"] == pd.Timestamp("2024-02-10"), "trip_count"] = 9999
        comparison_columns = ["demand_date", *MODEL_FEATURES]
        first = build_features(original).loc[
            lambda frame: frame["demand_date"] <= "2024-02-10", comparison_columns
        ]
        second = build_features(mutated).loc[
            lambda frame: frame["demand_date"] <= "2024-02-10", comparison_columns
        ]
        pd.testing.assert_frame_equal(first, second)

    def test_gap_invalidates_lag_and_rolling_history(self):
        frame = daily_series(45)
        frame = frame.loc[frame["demand_date"] != pd.Timestamp("2024-01-31")]
        features = build_features(frame)
        after_gap = features.loc[features["demand_date"] == pd.Timestamp("2024-02-01")].iloc[0]
        self.assertTrue(pd.isna(after_gap["lag_1d"]))
        self.assertTrue(pd.isna(after_gap["rolling_mean_7d"]))
        self.assertFalse(after_gap["is_feature_complete"])

    def test_complete_rows_apply_28_day_warmup(self):
        complete = complete_feature_rows(build_features(daily_series()))
        self.assertEqual(complete["demand_date"].min(), pd.Timestamp("2024-01-29"))


if __name__ == "__main__":
    unittest.main()
