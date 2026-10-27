"""Fixed RF refit and post-fit scoring, without model selection or DB writes."""
from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
from time import perf_counter

import pandas as pd

from dss.contracts import ContractError
from dss.features import build_features, complete_feature_rows
from dss.models import RF_NAME, RF_SETTINGS, TrainingArtifact, train_random_forest
from dss.pipeline import _artifact_split
from dss.recommendation import fit_demand_thresholds


def _require_universe(artifact: TrainingArtifact, rows: pd.DataFrame) -> None:
    # A missing whole zone otherwise looks like a smaller but complete grid.
    expected = set(artifact.thresholds.pickup_location_id)
    if set(rows.pickup_location_id) != expected:
        raise ContractError("dense grid zone universe must match the saved artifact")


def _complete_window(dense: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    """Require the full dense grid, including warmup, before building features."""
    if start > end:
        raise ContractError("window start must not exceed end")
    dates = pd.to_datetime(dense.demand_date)
    window = dense.loc[dates.between(pd.Timestamp(start - timedelta(days=28)), pd.Timestamp(end))].copy()
    window["demand_date"] = pd.to_datetime(window.demand_date).dt.normalize()
    zones = dense[["pickup_zone_key", "pickup_location_id"]].drop_duplicates()
    if zones.empty or zones.pickup_zone_key.duplicated().any() or zones.pickup_location_id.duplicated().any():
        raise ContractError("grid must contain unique eligible zones")
    expected = pd.MultiIndex.from_product(
        [pd.date_range(start - timedelta(days=28), end), range(24), zones.pickup_zone_key],
        names=["demand_date", "demand_hour", "pickup_zone_key"])
    actual = pd.MultiIndex.from_frame(window[list(expected.names)])
    if actual.has_duplicates or len(actual) != len(expected) or not expected.isin(actual).all():
        raise ContractError("complete dense grid required for fit/evaluation and 28-day history")
    features = complete_feature_rows(build_features(window))
    rows = features.loc[features.demand_date.between(pd.Timestamp(start), pd.Timestamp(end))].reset_index(drop=True)
    if len(rows) != ((end - start).days + 1) * 24 * len(zones):
        raise ContractError("complete feature rows required throughout window")
    return rows


def refit_from_dense(parent: TrainingArtifact, dense: pd.DataFrame, *, fit_start: date,
                     fit_end: date, git_commit_sha: str) -> TrainingArtifact:
    """Fit the frozen configuration on every eligible row; never compare models."""
    split = _artifact_split(parent)
    if (parent.selected_approach != RF_NAME or parent.random_forest is None
            or getattr(parent, "fit_end_date", None) is not None):
        raise ContractError("refit requires original validation-selected RF artifact")
    if parent.random_forest.metadata["hyperparameters"] != RF_SETTINGS:
        raise ContractError("selected RF settings do not match frozen configuration")
    regressor = parent.random_forest.estimator.named_steps["regressor"]
    if any(regressor.get_params()[key] != value for key, value in RF_SETTINGS.items()):
        raise ContractError("selected RF estimator disagrees with frozen settings")
    if fit_start != split.train_start or fit_end < split.validation_end:
        raise ContractError("refit must start at selection training start and include validation")
    # Cut future rows before feature construction and estimator fitting.
    q1 = dense.loc[pd.to_datetime(dense.demand_date).le(pd.Timestamp(fit_end))]
    _require_universe(parent, q1)
    training = _complete_window(q1, fit_start, fit_end)
    started = perf_counter()
    forest = train_random_forest(training)
    result = deepcopy(parent)
    result.random_forest = forest
    result.thresholds = fit_demand_thresholds(training)
    result.git_commit_sha = git_commit_sha
    result.fit_start_date, result.fit_end_date = fit_start.isoformat(), fit_end.isoformat()
    result.experiment_metadata = {
        "kind": "fixed_rf_refit", "fit_seconds": perf_counter() - started,
        "selection": {"config": deepcopy(parent.config), "validation_metrics": deepcopy(parent.validation_metrics),
                      "git_commit_sha": parent.git_commit_sha,
                      "experiment_metadata": deepcopy(parent.experiment_metadata)},
        "actual_fit": forest.metadata,
        "march_status": "fit data; not test", "publication": "offline only",
    }
    return result


def evaluation_rows(artifact: TrainingArtifact, dense: pd.DataFrame,
                    start: date, end: date) -> pd.DataFrame:
    """Vectorized rolling-origin features: shifted by day within zone/hour.

    Prior evaluation days' actuals may supply lags; target D and later days
    cannot enter features for D. The estimator is never refitted here.
    """
    fit_end = getattr(artifact, "fit_end_date", None)
    if fit_end is None or start <= date.fromisoformat(fit_end):
        raise ContractError("evaluation must be strictly after actual fit")
    if start <= _artifact_split(artifact).validation_end:
        raise ContractError("evaluation must follow selection validation")
    _require_universe(artifact, dense)
    return _complete_window(dense, start, end)
