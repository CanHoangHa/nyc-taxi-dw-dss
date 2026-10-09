"""Reproducible scikit-learn candidate model for count demand."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from dss.contracts import ContractError
from dss.features import MODEL_FEATURES


MODEL_NAME = "hist_gradient_boosting_poisson"
MODEL_VERSION = "1.0.0"
FEATURE_VERSION = "1.0.0"


@dataclass
class DemandModel:
    estimator: HistGradientBoostingRegressor
    metadata: dict[str, Any]

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        matrix = _feature_matrix(features)
        raw = self.estimator.predict(matrix)
        return np.maximum(0.0, raw.astype("float64"))


@dataclass
class TrainingArtifact:
    """Auditable output of validation-time model selection."""

    candidate: DemandModel
    thresholds: pd.DataFrame
    selected_approach: str
    validation_metrics: dict[str, dict[str, float]]
    config: dict[str, Any]
    git_commit_sha: str


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
    return value


def _feature_matrix(features: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in MODEL_FEATURES if column not in features.columns]
    if missing:
        raise ContractError("model frame is missing features: " + ", ".join(missing))
    matrix = features.loc[:, MODEL_FEATURES].apply(pd.to_numeric, errors="raise")
    values = matrix.to_numpy(dtype="float64")
    if not np.isfinite(values).all():
        raise ContractError("model features must be complete and finite")
    return matrix
