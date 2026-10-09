"""Candidate model training, prediction, and artifact tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from dss.features import build_features, complete_feature_rows
from dss.models import load_model, save_model, train_candidate
from tests.dss.test_features import daily_series


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.features = complete_feature_rows(build_features(daily_series(70)))

    def test_candidate_produces_non_negative_prediction(self):
        model = train_candidate(self.features, max_iter=10, max_leaf_nodes=5)
        prediction = model.predict(self.features.tail(5))
        self.assertEqual(prediction.shape, (5,))
        self.assertTrue(np.isfinite(prediction).all())
        self.assertTrue((prediction >= 0).all())
        self.assertEqual(model.metadata["training_row_count"], len(self.features))

    def test_artifact_round_trip_and_no_overwrite(self):
        model = train_candidate(self.features, max_iter=5, max_leaf_nodes=3)
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            path = Path(directory) / "candidate.joblib"
            save_model(model, path)
            loaded = load_model(path)
            np.testing.assert_allclose(
                model.predict(self.features.tail(3)),
                loaded.predict(self.features.tail(3)),
            )
            with self.assertRaises(FileExistsError):
                save_model(model, path)


if __name__ == "__main__":
    unittest.main()
