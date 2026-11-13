"""Reproduce the fixed Q1 experiment without ingestion or warehouse rebuild.

Run from repo root with PYTHONPATH=src. Saves a new immutable artifact and a
report; optionally persists a new forecast run. March 16--31 is retrospective.
"""
import argparse
from datetime import date, timedelta
import json
import hashlib
from time import perf_counter
from pathlib import Path

import numpy as np

from dss.config import load_config
from dss.models import load_training_artifact, RF_SETTINGS
from dss.pipeline import (load_dense_dataset, train_from_dense, _git_sha,
                          forecast_from_history, run_forecast, source_provenance)
from dss.models import save_training_artifact
from dss.ranking import rank_zone_interval, evaluate_top_k
from dss.repository import DemandRepository
from dss.service import DssService
from uuid import uuid4


def save_source_snapshot(directory, provenance):
    directory.mkdir(parents=True, exist_ok=False)
    for relative, expected_hash in provenance["sha256"].items():
        content = Path(relative).read_bytes()
        if hashlib.sha256(content).hexdigest() != expected_hash:
            raise RuntimeError(f"source changed during experiment: {relative}; rerun before saving")
        target = directory / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--persist-forecast", action="store_true")
    parser.add_argument("--artifact", type=Path, help="Resume scoring an existing RF artifact without refitting")
    arguments = parser.parse_args()
    config = load_config(Path("configs/dss_q1.toml"))
    source = DemandRepository()
    print("Fixed RF settings: " + json.dumps(RF_SETTINGS), flush=True)
    print("Loading existing Q1 mart (read only)...", flush=True)
    dense = load_dense_dataset(source, config.dataset_start, config.dataset_end)
    total_training_seconds = None
    if arguments.artifact:
        path = arguments.artifact
    else:
        print(f"Training four methods from {len(dense)} dense cells...", flush=True)
        started = perf_counter()
        artifact = train_from_dense(dense, config, git_commit_sha=_git_sha())
        total_training_seconds = perf_counter() - started
        path = config.artifact_directory / f"dss-rf-{uuid4()}.joblib"
        save_source_snapshot(path.with_suffix(".source"), artifact.experiment_metadata["source"])
        save_training_artifact(artifact, path)
    artifact = load_training_artifact(path)
    if getattr(artifact, "random_forest", None) is None:
        raise ValueError("comparison requires an RF experiment artifact")
    if artifact.config["split"] != {key: getattr(config.split, key).isoformat()
                                   for key in config.split.__dataclass_fields__}:
        raise ValueError("comparison split must match saved artifact")
    evaluation_source = source_provenance()
    evaluation_snapshot = path.with_name(path.stem + f"-evaluation-{uuid4()}.source")
    save_source_snapshot(evaluation_snapshot, evaluation_source)
    print(json.dumps({"artifact": str(path), "selected": artifact.selected_approach,
                      "validation": artifact.validation_metrics,
                      "train": artifact.experiment_metadata["train_metrics"],
                      "fit_seconds": artifact.experiment_metadata["fit_seconds"]}), flush=True)
    # Fixed illustrative policy, set before looking at March 16 actuals.
    day, borough, start, end, k = date(2024, 3, 16), "Manhattan", 6, 10, 10
    history = dense.loc[dense.demand_date.between(str(day-timedelta(days=28)), str(day-timedelta(days=1)))]
    forecast = forecast_from_history(artifact, history, source.eligible_zones(), day)
    from dss.persistence import ForecastRepository
    reference = ForecastRepository().ranking_zones()
    ranking = rank_zone_interval(forecast, borough=borough, start_hour=start, end_hour=end, zone_reference=reference)
    scores = evaluate_top_k(ranking, dense, k=k)
    report = {"artifact": str(path), "base_commit": _git_sha(),
              "source": artifact.experiment_metadata["source"],
              "source_snapshot": str(path.with_suffix(".source")),
              "evaluation_source": evaluation_source, "evaluation_source_snapshot": str(evaluation_snapshot),
              "total_training_seconds": total_training_seconds,
              "fit_seconds": artifact.experiment_metadata["fit_seconds"],
              "train": artifact.experiment_metadata["train_metrics"], "selected": artifact.selected_approach,
              "validation": artifact.validation_metrics,
              "ranking_evaluation": {"status": "retrospective/exploratory",
                  "forecast_date": str(day), "borough": borough, "start_hour": start,
                  "end_hour_exclusive": end, "k": k, "scores": scores},
              "interpretation": "Pickup concentration only; no evidence of dispatch effectiveness."}
    if arguments.persist_forecast:
        run_id, count = run_forecast(artifact, day)
        report["run_id"], report["forecast_rows"] = str(run_id), count
        service_ranking = DssService().zone_ranking(day, borough=borough, start_hour=start, end_hour=end)
        np.testing.assert_allclose(service_ranking.predicted_trip_count, ranking.predicted_trip_count)
        # Independent SQL sums reconcile the service with the stored run.
        from taxi_dw.db import open_connection
        with open_connection() as connection:
            sql = connection.execute(
                "SELECT pickup_location_id, sum(predicted_trip_count), sum(baseline_trip_count) "
                "FROM dss.zone_hour_forecast WHERE run_id=%s AND forecast_date=%s "
                "AND borough=%s AND is_actionable AND demand_hour >= %s AND demand_hour < %s "
                "GROUP BY pickup_location_id ORDER BY sum(predicted_trip_count) DESC, pickup_location_id",
                (run_id, day, borough, start, end)).fetchall()
        assert [row[0] for row in sql] == ranking.pickup_location_id.tolist()
        np.testing.assert_allclose([float(row[1]) for row in sql], ranking.predicted_trip_count)
        np.testing.assert_allclose([float(row[2]) for row in sql], ranking.baseline_trip_count)
        report["db_reconciliation"] = "passed"
    output = path.with_name(path.stem + f"-report-{uuid4()}.json")
    output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    print("Report: " + str(output), flush=True)


if __name__ == "__main__":
    main()
