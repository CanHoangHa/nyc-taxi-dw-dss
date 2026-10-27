"""Contracts for Random Forest and interval zone ranking."""
from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from dss.contracts import ContractError
from dss.features import build_features, complete_feature_rows
from dss.models import (train_random_forest, save_model, load_model, save_training_artifact,
                        load_training_artifact)
from dss.pipeline import train_from_dense, evaluate_from_dense, forecast_from_history
from tests.dss.test_pipeline import dense, q1_config
from tests.dss.fixtures import eligible_zones
from dss.service import DssService
from dss.ranking import rank_zone_interval, evaluate_top_k
from tests.dss.test_features import daily_series


def zone_reference():
    return forecasts()[["pickup_location_id", "borough", "zone_name", "is_actionable"]].drop_duplicates()


def forecasts():
    return pd.DataFrame([
        dict(forecast_date=date(2024, 3, 16), pickup_location_id=z,
             borough=b, zone_name=str(z), demand_hour=h, is_actionable=z < 264,
             predicted_trip_count=p, baseline_trip_count=10-p, demand_level="Low")
        for z, b, p in [(1, "Queens", 4), (2, "Queens", 4),
                        (3, "Queens", 0), (4, "Manhattan", 9), (264, "Queens", 20)]
        for h in range(6, 11)
    ])


class RandomForestTests(unittest.TestCase):
    def test_archived_glm_is_explicitly_rejected_even_if_baseline_selected(self):
        artifact = train_from_dense(dense(), q1_config(), git_commit_sha="test")
        artifact.poisson = object()  # State retained by the archived experimental pickle.
        artifact.selected_approach = "same_weekday_median"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "archived.joblib"
            save_training_artifact(artifact, path)
            with self.assertRaisesRegex(ContractError, "Poisson regression.*no longer supported"):
                load_training_artifact(path)
        with self.assertRaisesRegex(ContractError, "Poisson regression"):
            evaluate_from_dense(artifact, dense(), q1_config())

    def test_pipeline_train_only_and_training_artifact_compatibility(self):
        frame, config = dense(), q1_config()
        with patch("dss.pipeline.train_random_forest", wraps=train_random_forest) as fit:
            artifact = train_from_dense(frame, config, git_commit_sha="test")
        train = fit.call_args.args[0]
        self.assertEqual(train.demand_date.max().date(), config.split.train_end)
        self.assertEqual(artifact.selected_approach, min(artifact.validation_metrics,
                         key=lambda name: artifact.validation_metrics[name]["wape"]))
        history = frame.loc[frame.demand_date.lt("2024-02-21")]
        artifact.selected_approach = "random_forest"
        forecast = forecast_from_history(artifact, history, eligible_zones(), date(2024, 2, 21))
        self.assertTrue(np.isfinite(forecast.predicted_trip_count).all())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "new.joblib"
            save_training_artifact(artifact, path)
            loaded = load_training_artifact(path)
            self.assertIn("random_forest", evaluate_from_dense(loaded, frame, config))
            # Simulate an old pickled instance's state (no new field).
            del artifact.random_forest
            artifact.selected_approach = "same_weekday_median"
            path = Path(directory) / "legacy.joblib"
            save_training_artifact(artifact, path)
            loaded = load_training_artifact(path)
            self.assertEqual(len(evaluate_from_dense(loaded, frame, config)), 3)
            self.assertEqual(len(forecast_from_history(loaded, history, eligible_zones(), date(2024, 2, 21))), 48)

    def test_train_only_categorical_and_round_trip(self):
        train = complete_feature_rows(build_features(daily_series(70)))
        model = train_random_forest(train)
        preprocessing = model.estimator.named_steps["preprocess"]
        encoder = preprocessing.named_transformers_["categorical"]
        self.assertEqual(encoder.categories_[0].tolist(), sorted(train.pickup_location_id.unique()))
        original_categories = encoder.categories_[0].copy()
        future = train.tail(3).copy()
        future["pickup_location_id"] = 999
        future["lag_1d"] = 1000
        prediction = model.predict(future)
        self.assertTrue(np.isfinite(prediction).all())
        self.assertTrue((prediction >= 0).all())
        np.testing.assert_array_equal(original_categories, encoder.categories_[0])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rf.joblib"
            save_model(model, path)
            np.testing.assert_allclose(prediction, load_model(path).predict(future))


class RankingTests(unittest.TestCase):
    def test_service_detects_missing_whole_zone_with_one_bulk_reference_read(self):
        from tests.dss.test_service import FakeRepository
        from unittest.mock import Mock
        repo = FakeRepository()
        repo.read_forecasts = lambda *args, **kwargs: forecasts().loc[lambda f: f.pickup_location_id.ne(2)]
        repo.ranking_zones = Mock(return_value=zone_reference())
        with self.assertRaisesRegex(ContractError, "missing forecast.*2"):
            DssService(repo).zone_ranking(date(2024, 3, 16), borough="Queens", start_hour=6, end_hour=10)
        repo.ranking_zones.assert_called_once_with()

    def test_reference_detects_absent_zone_and_distinguishes_invalid_scope(self):
        rows = forecasts().loc[lambda frame: frame.pickup_location_id.ne(2)]
        for ids in [(), (1, 2)]:
            with self.subTest(ids=ids):
                with self.assertRaisesRegex(ContractError, "missing forecast.*2"):
                    self.rank(rows, zone_ids=ids, zone_reference=zone_reference())
        for ids, message in [((4,), "outside borough"), ((264,), "not operationally eligible"),
                             ((999,), "unknown requested")]:
            with self.assertRaisesRegex(ContractError, message):
                self.rank(rows, zone_ids=ids, zone_reference=zone_reference())
        with self.assertRaisesRegex(ContractError, "missing forecast"):
            self.rank(rows.iloc[:0], zone_reference=zone_reference())

    def test_invalid_measure_and_reference_disagreement(self):
        for value in [-1, np.inf, -np.inf]:
            with self.assertRaises(ContractError):
                self.rank(forecasts().assign(predicted_trip_count=value))
        rows = forecasts()
        rows.loc[rows.pickup_location_id.eq(2), "is_actionable"] = False
        with self.assertRaisesRegex(ContractError, "disagrees"):
            self.rank(rows, zone_reference=zone_reference())

    def test_requested_zone_missing_entirely_is_not_silently_dropped(self):
        rows = forecasts().loc[lambda frame: frame.pickup_location_id.ne(2)]
        with self.assertRaisesRegex(ContractError, "missing.*2"):
            self.rank(rows, zone_ids=(1, 2))

    def test_last_hour_and_full_day_boundaries(self):
        rows = forecasts()
        base = rows.loc[rows.demand_hour.eq(6)].copy()
        full = pd.concat([base.assign(demand_hour=hour) for hour in range(24)])
        last = rank_zone_interval(full, zone_reference=zone_reference(), borough="Queens", start_hour=23, end_hour=24)
        day = rank_zone_interval(full, zone_reference=zone_reference(), borough="Queens", start_hour=0, end_hour=24)
        self.assertEqual(last.predicted_trip_count.tolist(), [4, 4, 0])
        self.assertEqual(day.predicted_trip_count.tolist(), [96, 96, 0])
        self.assertTrue(rank_zone_interval(full, zone_reference=zone_reference(), borough="Bronx", start_hour=0, end_hour=24).empty)

    def test_service_keeps_hourly_inclusive_and_adds_half_open_ranking(self):
        from tests.dss.test_service import FakeRepository
        repo = FakeRepository()
        repo.read_forecasts = lambda *args, **kwargs: forecasts()
        repo.ranking_zones = lambda: zone_reference()
        service = DssService(repo)
        ranked = service.zone_ranking(date(2024, 3, 16), borough="Queens", start_hour=6, end_hour=10)
        self.assertEqual(ranked.predicted_trip_count.tolist(), [16, 16, 0])
        details = service.ranked_recommendations(date(2024, 3, 16), borough="Queens", hour_range=(6, 10), zone_ids=(1,))
        self.assertEqual(len(details), 5)

    def rank(self, rows=None, **kwargs):
        kwargs.setdefault("zone_reference", zone_reference())
        return rank_zone_interval(forecasts() if rows is None else rows,
                                  borough="Queens", start_hour=6, end_hour=10, **kwargs)

    def test_interval_ties_eligibility_and_zero(self):
        ranked = self.rank()
        self.assertEqual(ranked.pickup_location_id.tolist(), [1, 2, 3])
        self.assertEqual(ranked.predicted_trip_count.tolist(), [16, 16, 0])
        self.assertEqual(ranked.baseline_trip_count.tolist(), [24, 24, 40])
        self.assertEqual(ranked["rank"].tolist(), [1, 1, 3])
        self.assertIn("0", ranked.iloc[-1].ranking_reason)

    def test_missing_duplicate_invalid_or_mixed_day_rejected(self):
        rows = forecasts()
        for broken in (rows.drop(index=0), pd.concat([rows, rows.iloc[:1]]),
                       rows.assign(predicted_trip_count=np.nan),
                       rows.assign(forecast_date=[date(2024, 3, 17)] + rows.forecast_date.tolist()[1:])):
            with self.subTest():
                with self.assertRaises(ContractError):
                    self.rank(broken)
        for start, end in [(10, 6), (6, 6), (0, 25)]:
            with self.assertRaises(ContractError):
                rank_zone_interval(rows, zone_reference=zone_reference(), borough="Queens", start_hour=start, end_hour=end)

    def test_equal_k_tie_policy_actual_alignment_and_undefined_share(self):
        ranked = self.rank()
        actual = forecasts().rename(columns={"forecast_date": "demand_date"})
        actual["trip_count"] = actual.pickup_location_id * 2
        scores = evaluate_top_k(ranked, actual, k=1)
        self.assertEqual(scores["forecast"]["zone_ids"], [1])
        self.assertEqual(scores["d_minus_7"]["zone_ids"], [3])
        self.assertEqual(scores["forecast"]["actual_pickups"], 8)
        self.assertAlmostEqual(scores["forecast"]["actual_share"], 1/6)
        actual["trip_count"] = 0
        self.assertIsNone(evaluate_top_k(ranked, actual, k=1)["forecast"]["actual_share"])
        with self.assertRaises(ContractError):
            evaluate_top_k(ranked, actual.drop(index=0), k=1)
        with self.assertRaises(ContractError):
            evaluate_top_k(ranked, actual, k=4)


if __name__ == "__main__":
    unittest.main()
