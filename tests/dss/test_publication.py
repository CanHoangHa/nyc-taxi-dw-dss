"""Publication keeps selection, actual fit and historical results distinct."""
from copy import deepcopy
from dataclasses import replace
from datetime import date
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from dss.config import config_as_dict
from dss.contracts import ContractError
from dss.models import DemandModel, TrainingArtifact, load_publication_artifact, save_training_artifact
from dss.persistence import ForecastRepository
from dss.pipeline import forecast_from_history, run_forecast
from dss.recommendation import fit_demand_thresholds
from tests.dss.fixtures import eligible_zones
from tests.dss.test_pipeline import dense, q1_config
from tests.dss import test_persistence as persistence_fixtures
from tests.dss.test_persistence import FakeConnection, forecast_rows


class ConstantEstimator:
    def predict(self, matrix):
        return np.full(len(matrix), 2.0)


def artifact(refit=True):
    model = DemandModel(ConstantEstimator(), {
        "model_name": "random_forest", "train_start_date": "2024-01-29",
        "train_end_date": "2024-03-31" if refit else "2024-02-10",
    })
    return TrainingArtifact(
        candidate=None, random_forest=model,
        thresholds=fit_demand_thresholds(dense(91)), selected_approach="random_forest",
        validation_metrics={"random_forest": {"wape": 0.17}},
        config=config_as_dict(q1_config()), git_commit_sha="saved-source",
        fit_start_date="2024-01-29" if refit else None,
        fit_end_date="2024-03-31" if refit else None,
        experiment_metadata={"fit_seconds": 337.5229522,
                             "actual_fit": deepcopy(model.metadata)} if refit else {},
    )


class CaptureRepository:
    def save_run(self, metadata, forecasts):
        self.metadata, self.forecasts = metadata, forecasts
        return "saved-run"


class PublicationTests(unittest.TestCase):
    def publish(self, model):
        sink = CaptureRepository()
        with patch("dss.pipeline.load_dense_dataset", return_value=dense(91)):
            run_forecast(model, date(2024, 4, 1), demand_repository=Source(),
                         forecast_repository=sink, artifact_sha256="a" * 64)
        return sink

    def test_refit_publishes_actual_fit_without_relabelling_selection_metrics(self):
        sink = self.publish(artifact())
        meta = sink.metadata
        self.assertEqual(meta.train_end_date, date(2024, 2, 10))
        self.assertEqual(meta.validation_end_date, date(2024, 2, 20))
        self.assertEqual(meta.fit_end_date, date(2024, 3, 31))
        self.assertEqual(meta.fit_start_date, date(2024, 1, 29))
        self.assertEqual(meta.fit_kind, "refit")
        self.assertAlmostEqual(meta.fit_seconds, 337.5229522)
        self.assertEqual(meta.artifact_sha256, "a" * 64)
        self.assertNotIn("validation", meta.metrics)
        self.assertEqual(meta.metrics["selection_validation"], {"random_forest": {"wape": 0.17}})
        self.assertEqual(len(sink.forecasts), 48)

    def test_legacy_without_optional_attributes_still_publishes(self):
        model = artifact(False)
        del model.fit_start_date, model.fit_end_date, model.experiment_metadata
        meta = self.publish(model).metadata
        self.assertEqual(meta.fit_kind, "selection")
        self.assertEqual(meta.fit_end_date, date(2024, 2, 10))
        self.assertIn("validation", meta.metrics)

    def test_forecast_must_follow_both_selection_validation_and_actual_fit(self):
        for day in (date(2024, 2, 20), date(2024, 3, 31)):
            with self.subTest(day=day), self.assertRaises(ContractError):
                forecast_from_history(artifact(), dense(91), eligible_zones(), day)

    def test_partial_or_disagreeing_fit_metadata_cannot_be_published(self):
        for change in ("partial", "disagree"):
            model = artifact()
            if change == "partial":
                model.fit_start_date = None
            else:
                model.fit_end_date = "2024-03-30"
            with self.subTest(change=change), self.assertRaisesRegex(ContractError, "fit"):
                self.publish(model)

    def test_history_must_end_on_d_minus_one_and_have_full_zone_universe(self):
        model = artifact()
        for history in (dense(90), dense(92), dense(91).loc[lambda f: f.pickup_location_id.eq(1)]):
            with self.subTest(rows=len(history)), self.assertRaises(ContractError):
                forecast_from_history(model, history, eligible_zones(), date(2024, 4, 1))

    def test_persistence_rejects_forecast_inside_fit_before_transaction(self):
        meta = replace(persistence_fixtures.PersistenceTests().metadata(), fit_kind="refit",
                       fit_start_date=date(2024, 1, 1), fit_end_date=date(2024, 4, 1))
        with self.assertRaisesRegex(ContractError, "after"):
            ForecastRepository(FakeConnection()).save_run(meta, forecast_rows())

    def test_publication_checks_manifest_and_keeps_legacy_joblib_loadable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.joblib"
            model = artifact()
            model.experiment_metadata["selection"] = {
                "config": model.config, "validation_metrics": model.validation_metrics}
            save_training_artifact(model, path)
            with self.assertRaisesRegex(ContractError, "manifest"):
                load_publication_artifact(path)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            manifest = {"artifact_sha256": digest, "files_sha256": {path.name: digest},
                        "metadata": model.experiment_metadata}
            manifest_path = path.parent / "manifest.json"
            manifest_path.write_text(json.dumps(manifest))
            self.assertEqual(load_publication_artifact(path)[1], digest)
            manifest["artifact_sha256"] = "0" * 64
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ContractError, "SHA256"):
                load_publication_artifact(path)
            legacy_path = path.parent / "legacy" / "old.joblib"
            save_training_artifact(artifact(False), legacy_path)
            self.assertEqual(load_publication_artifact(legacy_path)[0].selected_approach, "random_forest")


class Source:
    def eligible_zones(self):
        return eligible_zones()
