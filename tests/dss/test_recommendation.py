"""Boundary tests for deterministic demand recommendations."""

from __future__ import annotations

import unittest

import pandas as pd

from dss.recommendation import add_recommendations, fit_demand_thresholds


class RecommendationTests(unittest.TestCase):
    def setUp(self):
        self.thresholds = pd.DataFrame(
            {
                "pickup_location_id": [1],
                "demand_hour": [8],
                "historical_p50": [10.0],
                "historical_p75": [20.0],
            }
        )

    def row(self, prediction: float, baseline: float, actionable: bool = True):
        return pd.DataFrame(
            {
                "pickup_location_id": [1],
                "demand_hour": [8],
                "predicted_trip_count": [prediction],
                "baseline_trip_count": [baseline],
                "is_actionable": [actionable],
            }
        )

    def test_high_requires_p75_and_ratio_boundary(self):
        result = add_recommendations(self.row(23, 20), self.thresholds)
        self.assertEqual(result.loc[0, "demand_level"], "High")
        self.assertAlmostEqual(result.loc[0, "demand_ratio"], 1.15)

    def test_p75_without_ratio_is_medium(self):
        result = add_recommendations(self.row(20, 20), self.thresholds)
        self.assertEqual(result.loc[0, "demand_level"], "Medium")

    def test_low_and_smoothed_zero_baseline(self):
        result = add_recommendations(self.row(0.5, 0), self.thresholds)
        self.assertEqual(result.loc[0, "demand_level"], "Low")
        self.assertEqual(result.loc[0, "demand_ratio"], 0.5)

    def test_non_actionable_zone_never_receives_dispatch_advice(self):
        result = add_recommendations(
            self.row(100, 1, actionable=False), self.thresholds
        )
        self.assertEqual(result.loc[0, "demand_level"], "Not applicable")
        self.assertIn("ngoài phạm vi", result.loc[0, "recommendation"])

    def test_thresholds_are_fit_per_zone_hour(self):
        training = pd.DataFrame(
            {
                "pickup_location_id": [1] * 4 + [2] * 4,
                "demand_hour": [8] * 4 + [9] * 4,
                "trip_count": [1, 2, 3, 4, 10, 20, 30, 40],
            }
        )
        thresholds = fit_demand_thresholds(training)
        self.assertEqual(len(thresholds), 2)
        self.assertEqual(thresholds.loc[0, "historical_p50"], 2.5)
        self.assertEqual(thresholds.loc[1, "historical_p75"], 32.5)


if __name__ == "__main__":
    unittest.main()
