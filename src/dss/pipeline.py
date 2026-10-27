"""Command-line orchestration for dataset, train, evaluate, and forecast."""

from __future__ import annotations

import argparse
from datetime import date, timedelta
import json
import hashlib
from pathlib import Path
import subprocess
from time import perf_counter
from typing import Sequence
from uuid import uuid4

import numpy as np
import pandas as pd

from dss.baseline import add_baseline_predictions, predict_baseline
from dss.config import DssConfig, config_as_dict, load_config
from dss.contracts import ContractError
from dss.dense_grid import build_dense_demand
from dss.evaluation import regression_metrics
from dss.features import build_features, complete_feature_rows
from dss.models import (
    FEATURE_VERSION,
    MODEL_NAME,
    MODEL_VERSION,
    TrainingArtifact,
    load_training_artifact,
    save_training_artifact,
    train_candidate,
    train_random_forest,
    RF_NAME,
    RF_VERSION,
    validate_supported_artifact,
)
from dss.persistence import ForecastRepository, ModelRunMetadata
from dss.recommendation import (
    RECOMMENDATION_VERSION,
    add_recommendations,
    fit_demand_thresholds,
)
from dss.repository import DemandRepository
from dss.split import TemporalSplit, split_by_date


APPROACH_MODEL = "model"
APPROACH_SEASONAL = "seasonal_naive"
APPROACH_MEDIAN = "same_weekday_median"


def load_dense_dataset(
    repository: DemandRepository, start_date: date, end_date: date
) -> pd.DataFrame:
    coverage = repository.coverage()
    zones = repository.eligible_zones()
    sparse = repository.sparse_demand(start_date, end_date)
    return build_dense_demand(
        sparse,
        coverage,
        zones,
        start_date=start_date,
        end_date=end_date,
    )


def train_from_dense(
    dense: pd.DataFrame, config: DssConfig, *, git_commit_sha: str
) -> TrainingArtifact:
    """Fit on train and select only from validation metrics."""

    features = complete_feature_rows(build_features(dense))
    parts = split_by_date(features, config.split)
    settings = config.model
    fit_start = perf_counter()
    candidate = train_candidate(
        parts.train,
        max_iter=settings.max_iter,
        learning_rate=settings.learning_rate,
        max_leaf_nodes=settings.max_leaf_nodes,
        random_state=settings.random_state,
    )
    boosting_fit_seconds = perf_counter() - fit_start
    validation = add_baseline_predictions(parts.validation)
    validation["prediction_model"] = candidate.predict(validation)
    fit_start = perf_counter()
    random_forest = train_random_forest(parts.train)
    forest_fit_seconds = perf_counter() - fit_start
    validation["prediction_random_forest"] = random_forest.predict(validation)
    prediction_columns = {
        APPROACH_MODEL: "prediction_model",
        APPROACH_SEASONAL: "prediction_seasonal_naive",
        APPROACH_MEDIAN: "prediction_same_weekday_median",
        RF_NAME: "prediction_random_forest",
    }
    metrics = {
        approach: regression_metrics(validation["trip_count"], validation[column])
        for approach, column in prediction_columns.items()
    }
    training = add_baseline_predictions(parts.train)
    training["prediction_model"] = candidate.predict(training)
    training["prediction_random_forest"] = random_forest.predict(training)
    train_metrics = {
        approach: regression_metrics(training["trip_count"], training[column])
        for approach, column in prediction_columns.items()
    }
    selected = min(
        metrics,
        key=lambda approach: _selection_wape(metrics[approach]["wape"]),
    )
    return TrainingArtifact(
        candidate=candidate,
        thresholds=fit_demand_thresholds(parts.train),
        selected_approach=selected,
        validation_metrics=metrics,
        config=config_as_dict(config),
        git_commit_sha=git_commit_sha,
        random_forest=random_forest,
        experiment_metadata={
            "experiment_version": "3.0.0",
            "selection_metric": "validation WAPE",
            "selection_tie_order": list(prediction_columns),
            "train_metrics": train_metrics,
            "fit_seconds": {APPROACH_MODEL: boosting_fit_seconds, RF_NAME: forest_fit_seconds,
                            APPROACH_SEASONAL: 0.0, APPROACH_MEDIAN: 0.0},
            "source": source_provenance(),
            "methods": {
                APPROACH_MODEL: candidate.metadata,
                RF_NAME: random_forest.metadata,
                APPROACH_SEASONAL: {"model_name": APPROACH_SEASONAL, "model_version": "1.0.0"},
                APPROACH_MEDIAN: {"model_name": APPROACH_MEDIAN, "model_version": "1.0.0"},
            },
            "test_status": "Q1 March 16-31 previously viewed; retrospective/exploratory only",
        },
    )


def _artifact_split(artifact: TrainingArtifact) -> TemporalSplit:
    """Read the immutable experiment boundaries used to fit and select models."""
    validate_supported_artifact(artifact)
    try:
        split = TemporalSplit(**{
            field: date.fromisoformat(artifact.config["split"][field])
            for field in TemporalSplit.__dataclass_fields__
        })
    except (KeyError, TypeError, ValueError) as error:
        raise ContractError("artifact must contain a valid saved temporal split") from error
    split.validate()
    return split


def evaluate_from_dense(
    artifact: TrainingArtifact, dense: pd.DataFrame, config: DssConfig
) -> dict[str, dict[str, float]]:
    """Open the test split after the validation-selected approach is frozen."""

    saved_split = _artifact_split(artifact)
    if getattr(artifact, "fit_end_date", None) is not None:
        raise ContractError("refit artifact requires separate post-fit evaluation; March is no longer holdout")
    if config.split != saved_split:
        raise ContractError("evaluation split must match the split saved in the artifact")
    features = complete_feature_rows(build_features(dense))
    test = add_baseline_predictions(split_by_date(features, saved_split).test)
    test["prediction_model"] = artifact.candidate.predict(test)
    columns = {
        APPROACH_MODEL: "prediction_model",
        APPROACH_SEASONAL: "prediction_seasonal_naive",
        APPROACH_MEDIAN: "prediction_same_weekday_median",
    }
    if getattr(artifact, "random_forest", None) is not None:
        test["prediction_random_forest"] = artifact.random_forest.predict(test)
        columns[RF_NAME] = "prediction_random_forest"
    return {
        approach: regression_metrics(test["trip_count"], test[column])
        for approach, column in columns.items()
    }


def forecast_from_history(
    artifact: TrainingArtifact,
    dense_history: pd.DataFrame,
    zones: pd.DataFrame,
    forecast_date: date,
) -> pd.DataFrame:
    """Create one 24 x eligible-zone day-ahead forecast from history through D-1."""

    saved_split = _artifact_split(artifact)
    fit_end = getattr(artifact, "fit_end_date", None)
    if fit_end is not None and forecast_date <= date.fromisoformat(fit_end):
        raise ContractError(f"forecast date must be after actual fit ending {fit_end}")
    if forecast_date <= saved_split.validation_end:
        raise ContractError(
            "forecast date must be after artifact training and validation data "
            f"(validation ends {saved_split.validation_end.isoformat()})"
        )
    if dense_history["demand_date"].max().date() != forecast_date - timedelta(days=1):
        raise ContractError("forecast history must end exactly on D-1")
    skeleton = pd.MultiIndex.from_product(
        [[pd.Timestamp(forecast_date)], range(24), zones["pickup_zone_key"]],
        names=["demand_date", "demand_hour", "pickup_zone_key"],
    ).to_frame(index=False)
    skeleton = skeleton.merge(zones, on="pickup_zone_key", validate="many_to_one")
    skeleton["trip_count"] = 0
    combined = pd.concat([dense_history, skeleton], ignore_index=True)
    feature_rows = build_features(combined).loc[
        lambda frame: frame["demand_date"].eq(pd.Timestamp(forecast_date))
    ]
    feature_rows = complete_feature_rows(feature_rows)
    expected = 24 * len(zones)
    if len(feature_rows) != expected:
        raise ContractError(
            f"forecast requires complete 28-day history for all cells; expected {expected}, got {len(feature_rows)}"
        )

    if artifact.selected_approach == APPROACH_MODEL:
        prediction = artifact.candidate.predict(feature_rows)
    elif artifact.selected_approach == RF_NAME and getattr(artifact, "random_forest", None) is not None:
        prediction = artifact.random_forest.predict(feature_rows)
    elif artifact.selected_approach in (APPROACH_SEASONAL, APPROACH_MEDIAN):
        prediction = predict_baseline(feature_rows, artifact.selected_approach).to_numpy()
    else:
        raise ContractError(f"unsupported selected approach: {artifact.selected_approach}")

    forecasts = feature_rows.loc[
        :,
        [
            "demand_date",
            "demand_hour",
            "pickup_zone_key",
            "pickup_location_id",
            "borough",
            "zone_name",
            "is_recommendation_eligible",
            "lag_7d",
        ],
    ].rename(
        columns={
            "demand_date": "forecast_date",
            "is_recommendation_eligible": "is_actionable",
            # Weekly change always compares with D-7, regardless of approach.
            # Demand levels use training quantiles separately from this ratio.
            "lag_7d": "baseline_trip_count",
        }
    )
    forecasts["predicted_trip_count"] = np.maximum(0.0, prediction)
    return add_recommendations(forecasts, artifact.thresholds)


def run_train(config: DssConfig, repository: DemandRepository | None = None) -> Path:
    source = repository or DemandRepository()
    dense = load_dense_dataset(source, config.dataset_start, config.dataset_end)
    artifact = train_from_dense(dense, config, git_commit_sha=_git_sha())
    path = config.artifact_directory / f"dss-{uuid4()}.joblib"
    save_training_artifact(artifact, path)
    return path


def run_forecast(
    artifact: TrainingArtifact,
    forecast_date: date,
    *,
    demand_repository: DemandRepository | None = None,
    forecast_repository: ForecastRepository | None = None,
) -> tuple[object, int]:
    if getattr(artifact, "fit_end_date", None) is not None:
        raise ContractError("refit artifacts are offline only; DB selection metadata cannot represent actual fit")
    source = demand_repository or DemandRepository()
    sink = forecast_repository or ForecastRepository()
    history_start = forecast_date - timedelta(days=28)
    history_end = forecast_date - timedelta(days=1)
    zones = source.eligible_zones()
    history = load_dense_dataset(source, history_start, history_end)
    forecasts = forecast_from_history(artifact, history, zones, forecast_date)
    split = artifact.config["split"]
    run_id = sink.save_run(
        ModelRunMetadata(
            model_name=(
                MODEL_NAME if artifact.selected_approach == APPROACH_MODEL
                else artifact.selected_approach
            ),
            model_version=RF_VERSION if artifact.selected_approach == RF_NAME else MODEL_VERSION,
            feature_version=FEATURE_VERSION,
            recommendation_version=RECOMMENDATION_VERSION,
            train_start_date=date.fromisoformat(split["train_start"]),
            train_end_date=date.fromisoformat(split["train_end"]),
            validation_start_date=date.fromisoformat(split["validation_start"]),
            validation_end_date=date.fromisoformat(split["validation_end"]),
            metrics={"validation": artifact.validation_metrics,
                     "experiment": getattr(artifact, "experiment_metadata", {})},
            git_commit_sha=artifact.git_commit_sha,
        ),
        forecasts,
    )
    return run_id, len(forecasts)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "build-dataset":
            dense = load_dense_dataset(
                DemandRepository(), arguments.start_date, arguments.end_date
            )
            arguments.output.parent.mkdir(parents=True, exist_ok=True)
            dense.to_parquet(arguments.output, index=False)
            print(json.dumps({"rows": len(dense), "output": str(arguments.output)}))
        elif arguments.command == "train":
            config = load_config(arguments.config)
            path = run_train(config)
            artifact = load_training_artifact(path)
            print(
                json.dumps(
                    {
                        "artifact": str(path),
                        "selected_approach": artifact.selected_approach,
                        "validation_metrics": artifact.validation_metrics,
                    }
                )
            )
        elif arguments.command == "evaluate":
            config = load_config(arguments.config)
            artifact = load_training_artifact(arguments.artifact)
            dense = load_dense_dataset(
                DemandRepository(), config.dataset_start, config.dataset_end
            )
            print(json.dumps({"test_metrics": evaluate_from_dense(artifact, dense, config)}))
        elif arguments.command == "forecast":
            artifact = load_training_artifact(arguments.artifact)
            run_id, rows = run_forecast(artifact, arguments.date)
            print(json.dumps({"run_id": str(run_id), "forecast_rows": rows}))
        return 0
    except (ContractError, FileNotFoundError, ValueError) as error:
        parser.exit(2, f"DSS {arguments.command} failed: {error}\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="NYC Taxi DSS pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    dataset = subparsers.add_parser("build-dataset")
    dataset.add_argument("--start-date", type=date.fromisoformat, required=True)
    dataset.add_argument("--end-date", type=date.fromisoformat, required=True)
    dataset.add_argument("--output", type=Path, required=True)

    train = subparsers.add_parser("train")
    train.add_argument("--config", type=Path, required=True)

    evaluate = subparsers.add_parser("evaluate")
    evaluate.add_argument("--config", type=Path, required=True)
    evaluate.add_argument("--artifact", type=Path, required=True)

    forecast = subparsers.add_parser("forecast")
    forecast.add_argument("--artifact", type=Path, required=True)
    forecast.add_argument("--date", type=date.fromisoformat, required=True)
    return parser


def _selection_wape(value: float) -> float:
    return value if np.isfinite(value) else float("inf")


def _git_sha() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def source_provenance() -> dict:
    """Hash a bounded allowlist of experiment sources, never local secrets/data."""
    root = Path(__file__).resolve().parents[2]
    paths = sorted({*root.glob("src/dss/*.py"), *root.glob("scripts/*.py"),
                    root / "src/dashboard/app.py", root / "configs/dss_q1.toml",
                    root / "requirements.txt", root / ".gitignore"})
    status = subprocess.run(["git", "-C", str(root), "status", "--porcelain"],
                            check=True, capture_output=True, text=True).stdout
    return {"git_commit_sha": _git_sha(), "working_tree_dirty": bool(status.strip()),
            "sha256": {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                       for path in paths}}


if __name__ == "__main__":
    raise SystemExit(main())
