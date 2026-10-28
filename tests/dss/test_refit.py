"""Refit boundaries and rolling-origin evaluation must remain independent."""
from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from dss.contracts import ContractError
from dss.models import RF_NAME, load_training_artifact, save_training_artifact
from dss.pipeline import train_from_dense, forecast_from_history, evaluate_from_dense, run_forecast
from tests.dss.test_pipeline import dense, q1_config
from tests.dss.fixtures import eligible_zones


class RefitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parent = train_from_dense(dense(), q1_config(), git_commit_sha="test")
        cls.parent.selected_approach = RF_NAME

    def refit(self, frame=None):
        from dss.refit import refit_from_dense
        return refit_from_dense(self.parent, dense(121) if frame is None else frame,
                                fit_start=date(2024, 1, 29), fit_end=date(2024, 3, 31),
                                git_commit_sha="refit-test")

    def test_refit_includes_all_q1_and_ignores_future_actuals(self):
        frame = dense(121)
        first = self.refit(frame)
        frame.loc[frame.demand_date.ge("2024-04-01"), "trip_count"] = 999999
        second = self.refit(frame)
        self.assertEqual(first.random_forest.metadata["training_row_count"], 63 * 48)
        self.assertEqual(first.config, self.parent.config)
        self.assertEqual(first.validation_metrics, self.parent.validation_metrics)
        self.assertEqual(first.fit_end_date, "2024-03-31")
        from dss.features import build_features, complete_feature_rows
        features = complete_feature_rows(build_features(dense(121))).tail(48)
        np.testing.assert_allclose(first.random_forest.predict(features), second.random_forest.predict(features))

    def test_missing_fit_cell_fails_instead_of_dropping_sample(self):
        frame = dense(121)
        frame = frame.drop(frame.loc[frame.demand_date.eq(pd.Timestamp("2024-03-31"))].index[0])
        with self.assertRaisesRegex(ContractError, "complete|grid"):
            self.refit(frame)

    def test_refit_blocks_march_holdout_and_forecasts_within_fit(self):
        artifact = self.refit()
        with self.assertRaisesRegex(ContractError, "fit"):
            forecast_from_history(artifact, dense(89), eligible_zones(), date(2024, 3, 31))
        with self.assertRaisesRegex(ContractError, "refit"):
            evaluate_from_dense(artifact, dense(), q1_config())
        with patch("dss.pipeline.DemandRepository") as repository:
            with self.assertRaisesRegex(ContractError, "after"):
                run_forecast(artifact, date(2024, 3, 31))
            repository.assert_not_called()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "refit.joblib"
            save_training_artifact(artifact, path)
            self.assertEqual(load_training_artifact(path).fit_end_date, "2024-03-31")

    def test_evaluation_features_exclude_same_day_and_future_but_use_prior_day(self):
        from dss.refit import evaluation_rows
        artifact = self.refit()
        frame = dense(121)
        rows = evaluation_rows(artifact, frame, date(2024, 4, 1), date(2024, 4, 30))
        self.assertEqual(len(rows), 30 * 48)
        changed = frame.copy()
        changed.loc[changed.demand_date.ge("2024-04-15"), "trip_count"] += 10000
        other = evaluation_rows(artifact, changed, date(2024, 4, 1), date(2024, 4, 30))
        from dss.features import MODEL_FEATURES
        pd.testing.assert_frame_equal(rows.loc[rows.demand_date.le("2024-04-15"), list(MODEL_FEATURES)],
                                      other.loc[other.demand_date.le("2024-04-15"), list(MODEL_FEATURES)])
        self.assertTrue((rows.loc[rows.demand_date.eq("2024-04-16"), "lag_1d"].to_numpy()
                         != other.loc[other.demand_date.eq("2024-04-16"), "lag_1d"].to_numpy()).all())
        with self.assertRaisesRegex(ContractError, "fit"):
            evaluation_rows(artifact, frame, date(2024, 3, 31), date(2024, 4, 30))

    def test_vectorized_evaluation_matches_daily_d_minus_one_forecasts(self):
        from dss.refit import evaluation_rows
        artifact = self.refit()
        frame = dense(121)
        rows = evaluation_rows(artifact, frame, date(2024, 4, 1), date(2024, 4, 30))
        for day in (date(2024, 4, 1), date(2024, 4, 15), date(2024, 4, 30)):
            stamp = pd.Timestamp(day)
            history = frame.loc[frame.demand_date.between(stamp - pd.Timedelta(days=28),
                                                        stamp - pd.Timedelta(days=1))]
            daily = forecast_from_history(artifact, history, eligible_zones(), day)
            expected = artifact.random_forest.predict(rows.loc[rows.demand_date.eq(stamp)])
            np.testing.assert_allclose(daily.predicted_trip_count, expected)

    def test_refit_rejects_different_selected_model_or_settings(self):
        from copy import deepcopy
        from dss.refit import refit_from_dense
        for kind in ("selection", "settings"):
            parent = deepcopy(self.parent)
            if kind == "selection":
                parent.selected_approach = "model"
            else:
                parent.random_forest.metadata["hyperparameters"]["max_depth"] = 5
            with self.assertRaises(ContractError):
                refit_from_dense(parent, dense(91), fit_start=date(2024, 1, 29),
                                 fit_end=date(2024, 3, 31), git_commit_sha="test")

    def test_missing_entire_zone_cannot_silently_shrink_fit_or_evaluation(self):
        from dss.refit import evaluation_rows
        frame = dense(121)
        reduced = frame.loc[frame.pickup_location_id.eq(1)]
        with self.assertRaisesRegex(ContractError, "universe"):
            self.refit(reduced)
        artifact = self.refit(frame)
        with self.assertRaisesRegex(ContractError, "universe"):
            evaluation_rows(artifact, reduced, date(2024, 4, 1), date(2024, 4, 30))
