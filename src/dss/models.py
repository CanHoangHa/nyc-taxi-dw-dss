"""Reproducible scikit-learn candidate model for count demand."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
import hashlib
import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
import sklearn

from dss.contracts import ContractError
from dss.features import MODEL_FEATURES


MODEL_NAME = "hist_gradient_boosting_poisson"
MODEL_VERSION = "1.0.0"
FEATURE_VERSION = "1.0.0"
RF_NAME = "random_forest"
RF_VERSION = "1.0.0"
RF_CATEGORICAL = ("pickup_location_id",)
RF_NUMERIC = tuple(c for c in MODEL_FEATURES if c not in RF_CATEGORICAL)


@dataclass
class DemandModel:
    estimator: Any
    metadata: dict[str, Any]

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        if self.metadata.get("model_name") == "poisson_regression":
            raise ContractError("experimental Poisson regression model is no longer supported")
        matrix = _feature_matrix(features)
        raw = self.estimator.predict(matrix)
        if not np.isfinite(raw).all():
            raise ContractError("model predictions must be finite")
        return np.maximum(0.0, raw.astype("float64"))


@dataclass
class TrainingArtifact:
    """Selection record, optionally carrying a separately dated RF refit."""

    candidate: DemandModel
    thresholds: pd.DataFrame
    selected_approach: str
    validation_metrics: dict[str, dict[str, float]]
    config: dict[str, Any]
    git_commit_sha: str
    # Default preserves loading legacy joblib instances without this attribute.
    random_forest: DemandModel | None = None
    experiment_metadata: dict[str, Any] = field(default_factory=dict)
    # Separate actual refit window from immutable selection train/validation.
    fit_start_date: str | None = None
    fit_end_date: str | None = None


def train_candidate(
    training: pd.DataFrame,
    *,
    max_iter: int = 100,
    learning_rate: float = 0.08,
    max_leaf_nodes: int = 31,
    random_state: int = 42,
) -> DemandModel:
    """Fit the initial Poisson gradient-boosting candidate on training only."""

    if "trip_count" not in training.columns:
        raise ContractError("training frame is missing trip_count")
    if training.empty:
        raise ContractError("training frame must not be empty")
    target = pd.to_numeric(training["trip_count"], errors="raise").to_numpy(
        dtype="float64"
    )
    if not np.isfinite(target).all() or (target < 0).any():
        raise ContractError("training target must be finite and non-negative")
    matrix = _feature_matrix(training)
    estimator = HistGradientBoostingRegressor(
        loss="poisson",
        learning_rate=learning_rate,
        max_iter=max_iter,
        max_leaf_nodes=max_leaf_nodes,
        random_state=random_state,
        early_stopping=False,
    )
    estimator.fit(matrix, target)
    dates = pd.to_datetime(training["demand_date"], errors="raise")
    metadata: dict[str, Any] = {
        "model_name": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "feature_version": FEATURE_VERSION,
        "trained_at": datetime.now(UTC).isoformat(),
        "training_row_count": int(len(training)),
        "train_start_date": dates.min().date().isoformat(),
        "train_end_date": dates.max().date().isoformat(),
        "feature_columns": list(MODEL_FEATURES),
        "hyperparameters": {
            "max_iter": max_iter,
            "learning_rate": learning_rate,
            "max_leaf_nodes": max_leaf_nodes,
            "random_state": random_state,
        },
    }
    return DemandModel(estimator=estimator, metadata=metadata)


RF_SETTINGS = dict(n_estimators=64, max_depth=16, min_samples_leaf=10,
                   max_features=0.7, n_jobs=2, random_state=42)


def train_random_forest(training: pd.DataFrame) -> DemandModel:
    """Bounded RF with train-only categorical zone encoding; trees need no scaling."""
    matrix = _feature_matrix(training)
    target = pd.to_numeric(training["trip_count"], errors="raise").to_numpy(dtype=float)
    if not len(target) or not np.isfinite(target).all() or (target < 0).any():
        raise ContractError("RF training target must be finite and non-negative")
    estimator = Pipeline([
        ("preprocess", ColumnTransformer([
            ("categorical", OneHotEncoder(handle_unknown="ignore", dtype=np.float32), list(RF_CATEGORICAL)),
            ("numeric", "passthrough", list(RF_NUMERIC)),
        ], sparse_threshold=1.0)),
        ("regressor", RandomForestRegressor(**RF_SETTINGS)),
    ])
    estimator.fit(matrix, target)
    dates = pd.to_datetime(training["demand_date"])
    return DemandModel(estimator, {
        "model_name": RF_NAME, "model_version": RF_VERSION,
        "feature_version": FEATURE_VERSION, "preprocessing_version": "rf-onehot-zone-1.0.0",
        "sklearn_version": sklearn.__version__, "trained_at": datetime.now(UTC).isoformat(),
        "training_row_count": len(training),
        "train_start_date": dates.min().date().isoformat(),
        "train_end_date": dates.max().date().isoformat(),
        "feature_columns": list(MODEL_FEATURES),
        "categorical_columns": list(RF_CATEGORICAL),
        "numeric_columns": list(RF_NUMERIC),
        "hyperparameters": RF_SETTINGS.copy(),
    })


def validate_supported_artifact(artifact: TrainingArtifact) -> None:
    """Experimental GLM artifacts are archived, not silently reinterpreted."""
    if getattr(artifact, "poisson", None) is not None or artifact.selected_approach == "poisson_regression":
        raise ContractError("experimental Poisson regression artifact is no longer supported; retain it for audit and train a new RF artifact")


def save_model(model: DemandModel, path: Path) -> Path:
    """Persist one immutable model artifact; refuse accidental overwrite."""

    target = Path(path)
    if target.exists():
        raise FileExistsError(f"model artifact already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, target)
    return target


def load_model(path: Path) -> DemandModel:
    """Load and minimally validate a trusted local model artifact."""

    value = joblib.load(Path(path))
    if not isinstance(value, DemandModel):
        raise ContractError("artifact is not a DSS DemandModel")
    if value.metadata.get("model_name") == "poisson_regression":
        raise ContractError("experimental Poisson regression model is no longer supported")
    return value


def save_training_artifact(artifact: TrainingArtifact, path: Path) -> Path:
    target = Path(path)
    if target.exists():
        raise FileExistsError(f"training artifact already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, target)
    return target


def load_training_artifact(path: Path) -> TrainingArtifact:
    value = joblib.load(Path(path))
    if not isinstance(value, TrainingArtifact):
        raise ContractError("artifact is not a DSS TrainingArtifact")
    validate_supported_artifact(value)
    return value


def actual_fit_window(artifact: TrainingArtifact) -> tuple[date, date, str]:
    """Resolve legacy selection fits and reject incomplete/inconsistent refits."""
    start = getattr(artifact, "fit_start_date", None)
    end = getattr(artifact, "fit_end_date", None)
    if start is None and end is None:
        split = artifact.config["split"]
        return date.fromisoformat(split["train_start"]), date.fromisoformat(split["train_end"]), "selection"
    try:
        start_date, end_date = date.fromisoformat(start), date.fromisoformat(end)
    except (TypeError, ValueError) as error:
        raise ContractError("actual fit requires valid start and end dates") from error
    forest = getattr(artifact, "random_forest", None)
    if (artifact.selected_approach != RF_NAME or forest is None
            or start_date != date.fromisoformat(artifact.config["split"]["train_start"])
            or end_date < date.fromisoformat(artifact.config["split"]["validation_end"])
            or forest.metadata.get("train_start_date") != start
            or forest.metadata.get("train_end_date") != end):
        raise ContractError("actual fit window must match the refitted RF and include selection data")
    return start_date, end_date, "refit"


def load_publication_artifact(path: Path) -> tuple[TrainingArtifact, str]:
    """Verify a refit's manifest before loading the trusted local joblib."""
    path = Path(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest_path = path.parent / "manifest.json"
    manifest = None
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (manifest.get("artifact_sha256") != digest
                or manifest.get("files_sha256", {}).get(path.name) != digest):
            raise ContractError("artifact SHA256 disagrees with publication manifest")
    artifact = load_training_artifact(path)
    _, _, kind = actual_fit_window(artifact)
    if kind == "refit":
        if manifest is None or manifest.get("metadata") != artifact.experiment_metadata:
            raise ContractError("refit publication requires a matching manifest and metadata")
        selection = artifact.experiment_metadata.get("selection", {})
        if (selection.get("config") != artifact.config
                or selection.get("validation_metrics") != artifact.validation_metrics
                or artifact.experiment_metadata.get("actual_fit") != artifact.random_forest.metadata):
            raise ContractError("refit manifest must preserve selection and actual fit metadata")
    return artifact, digest


def _feature_matrix(features: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in MODEL_FEATURES if column not in features.columns]
    if missing:
        raise ContractError("model frame is missing features: " + ", ".join(missing))
    matrix = features.loc[:, MODEL_FEATURES].apply(pd.to_numeric, errors="raise")
    values = matrix.to_numpy(dtype="float64")
    if not np.isfinite(values).all():
        raise ContractError("model features must be complete and finite")
    return matrix
