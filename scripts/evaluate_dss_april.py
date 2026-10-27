"""Frozen Q1 refit and April evaluation. Run refit first, then evaluate --artifact.

No model selection, ingestion, dashboard publication, or parameter search.
"""
import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import platform
from uuid import uuid4

import numpy as np
import pandas as pd
import sklearn

from dss.baseline import add_baseline_predictions
from dss.contracts import ContractError
from dss.evaluation import regression_metrics
from dss.models import load_training_artifact, save_training_artifact
from dss.pipeline import load_dense_dataset, source_provenance, _git_sha
from dss.ranking import rank_zone_interval, evaluate_top_k
from dss.refit import refit_from_dense, evaluation_rows
from dss.repository import DemandRepository
from taxi_dw.db import open_connection

PARENT = Path("artifacts/models/dss-rf-9a687651-d038-4f06-8ec2-1bbaa5946f3a.joblib")
PROTOCOL = Path("docs/dss_april_protocol.md")
START, END = date(2024, 4, 1), date(2024, 4, 30)
CASES = (("Manhattan", 8, 9, 10), ("Manhattan", 6, 10, 10))


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    # Undefined WAPE must be JSON null, never nonstandard NaN.
    def clean(item):
        if isinstance(item, dict):
            return {str(key): clean(value) for key, value in item.items()}
        if isinstance(item, (list, tuple)):
            return [clean(value) for value in item]
        if isinstance(item, float) and not np.isfinite(item):
            return None
        return item
    Path(path).write_text(json.dumps(clean(value), indent=2, allow_nan=False), encoding="utf-8")


def snapshot(directory):
    provenance = source_provenance()
    provenance["sha256"][PROTOCOL.as_posix()] = sha256(PROTOCOL)
    for relative, expected in provenance["sha256"].items():
        content = Path(relative).read_bytes()
        if hashlib.sha256(content).hexdigest() != expected:
            raise RuntimeError(f"source changed during snapshot: {relative}")
        target = directory / "source" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    provenance["versions"] = {"python": platform.python_version(), "pandas": pd.__version__,
                              "numpy": np.__version__, "sklearn": sklearn.__version__}
    return provenance


def audit_snapshot(directory):
    with open_connection() as connection:
        rows = connection.execute(
            "SELECT batch_id::text,source_year,source_month,source_file_sha256,"
            "source_row_count,loaded_row_count,valid_count,quarantined_count,rejected_count "
            "FROM audit.etl_batch WHERE status='succeeded' ORDER BY source_year,source_month"
        ).fetchall()
    write_json(directory / "audit.json", rows)


def run_refit():
    source = DemandRepository()
    directory = Path("artifacts/models") / f"dss-rf-q1-refit-{uuid4()}"
    directory.mkdir(parents=True, exist_ok=False)
    provenance = snapshot(directory)
    old = {str(path): sha256(path) for path in sorted(Path("artifacts/models").rglob("*.joblib"))}
    zones = source.eligible_zones()
    zones.to_parquet(directory / "zones.parquet", index=False)
    source.coverage().to_csv(directory / "coverage.csv", index=False)
    audit_snapshot(directory)
    print("Loading Q1 only; refitting fixed RF...", flush=True)
    dense = load_dense_dataset(source, date(2024, 1, 1), date(2024, 3, 31))
    dense.to_parquet(directory / "q1.parquet", index=False)
    parent = load_training_artifact(PARENT)
    artifact = refit_from_dense(parent, dense, fit_start=date(2024, 1, 29),
                                fit_end=date(2024, 3, 31), git_commit_sha=_git_sha())
    artifact.experiment_metadata.update({"source": provenance, "parent_artifact": str(PARENT),
        "parent_sha256": sha256(PARENT), "protocol_sha256": sha256(PROTOCOL),
        "q1_sha256": sha256(directory / "q1.parquet"),
        "zones_sha256": sha256(directory / "zones.parquet")})
    path = directory / "model.joblib"
    save_training_artifact(artifact, path)
    manifest = {"artifact": str(path), "artifact_sha256": sha256(path),
                "old_artifacts": old, "metadata": artifact.experiment_metadata,
                "files_sha256": {p.name: sha256(p) for p in directory.iterdir() if p.is_file()}}
    write_json(directory / "manifest.json", manifest)
    print(json.dumps({"artifact": str(path), "sha256": sha256(path),
                      "actual_fit": artifact.random_forest.metadata,
                      "fit_seconds": artifact.experiment_metadata["fit_seconds"]}), flush=True)


def run_evaluation(path):
    directory = path.parent
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if sha256(path) != manifest["artifact_sha256"]:
        raise ContractError("refit artifact checksum mismatch")
    artifact = load_training_artifact(path)
    metadata = artifact.experiment_metadata
    if metadata["protocol_sha256"] != sha256(PROTOCOL):
        raise ContractError("frozen protocol changed since refit")
    for old, expected in manifest["old_artifacts"].items():
        if sha256(old) != expected:
            raise ContractError(f"old artifact changed: {old}")
    source = DemandRepository()
    zones = pd.read_parquet(directory / "zones.parquet")
    if sha256(directory / "zones.parquet") != metadata["zones_sha256"]:
        raise ContractError("candidate snapshot checksum mismatch")
    pd.testing.assert_frame_equal(source.eligible_zones(), zones)
    output = directory / f"april-{uuid4()}"
    output.mkdir(exist_ok=False)
    provenance = snapshot(output)
    audit_snapshot(output)
    source.coverage().to_csv(output / "coverage.csv", index=False)
    dense = load_dense_dataset(source, date(2024, 1, 1), END)
    if sha256(directory / "q1.parquet") != metadata["q1_sha256"]:
        raise ContractError("Q1 input snapshot checksum mismatch")
    q1 = pd.read_parquet(directory / "q1.parquet")
    rebuilt_q1 = dense.loc[dense.demand_date.le("2024-03-31")].reset_index(drop=True)
    pd.testing.assert_frame_equal(q1, rebuilt_q1)
    dense.to_parquet(output / "history-actual.parquet", index=False)
    rows = add_baseline_predictions(evaluation_rows(artifact, dense, START, END))
    rows["prediction_rf"] = artifact.random_forest.predict(rows)
    parent = load_training_artifact(PARENT)
    if sha256(PARENT) != metadata["parent_sha256"]:
        raise ContractError("parent checksum mismatch")
    rows["prediction_rf_parent"] = parent.random_forest.predict(rows)
    columns = {"rf_refit": "prediction_rf", "rf_parent": "prediction_rf_parent",
               "d_minus_7": "prediction_seasonal_naive",
               "weekday_median": "prediction_same_weekday_median"}
    metrics = []
    for borough, group in [("ALL", rows), *rows.groupby("borough", observed=True)]:
        for method, column in columns.items():
            metrics.append({"borough": borough, "method": method,
                            **regression_metrics(group.trip_count, group[column])})
    pd.DataFrame(metrics).to_csv(output / "metrics.csv", index=False)
    rows.to_parquet(output / "predictions.parquet", index=False)
    reference = zones.rename(columns={"is_recommendation_eligible": "is_actionable"})
    daily = []
    for day, group in rows.groupby("demand_date", observed=True):
        forecasts = group.rename(columns={"demand_date": "forecast_date", "prediction_rf": "predicted_trip_count",
                                          "lag_7d": "baseline_trip_count",
                                          "is_recommendation_eligible": "is_actionable"})
        for borough, start, end, k in CASES:
            ranked = rank_zone_interval(forecasts, borough=borough, start_hour=start, end_hour=end,
                                        zone_reference=reference)
            scores = evaluate_top_k(ranked, group, k=k)
            delta = scores["forecast"]["actual_pickups"] - scores["d_minus_7"]["actual_pickups"]
            denominator = scores["forecast"]["candidate_actual_pickups"]
            daily.append({"date": str(day.date()), "borough": borough, "start": start, "end": end, "k": k,
                          "scores": scores, "pickup_delta": delta,
                          "share_delta_pp": 100 * delta / denominator if denominator else None,
                          "outcome": "win" if delta > 0 else "loss" if delta < 0 else "tie"})
    summaries = []
    for borough, start, end, k in CASES:
        subset = [row for row in daily if row["borough"] == borough and row["start"] == start and row["end"] == end]
        total = sum(row["scores"]["forecast"]["candidate_actual_pickups"] for row in subset)
        captures = {method: sum(row["scores"][method]["actual_pickups"] for row in subset)
                    for method in ("forecast", "d_minus_7")}
        deltas = [row["share_delta_pp"] for row in subset if row["share_delta_pp"] is not None]
        summaries.append({"borough": borough, "start": start, "end": end, "k": k, "days": len(subset),
            **{outcome: sum(row["outcome"] == outcome for row in subset) for outcome in ("win", "tie", "loss")},
            "mean_daily_share_delta_pp": float(np.mean(deltas)) if deltas else None,
            "pooled_shares": {method: value / total if total else None for method, value in captures.items()},
            "captured_pickups": captures, "candidate_actual_pickups": total})
    report = {"artifact": str(path), "artifact_sha256": sha256(path), "evaluation_source": provenance,
              "start": str(START), "end": str(END), "row_count": len(rows), "metrics": metrics,
              "q1_history_reconciliation": "identical to pre-ingestion Q1 snapshot",
              "ranking_summary": summaries, "ranking_daily": daily,
              "files_sha256": {p.name: sha256(p) for p in output.iterdir() if p.is_file()},
              "interpretation": "Observed pickup concentration only, not dispatch effectiveness or unmet demand."}
    write_json(output / "report.json", report)
    print(pd.DataFrame(metrics).to_string(index=False), flush=True)
    print(json.dumps(summaries, indent=2), flush=True)
    print("Report: " + str(output / "report.json"), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("command", choices=["refit", "evaluate"])
    parser.add_argument("--artifact", type=Path)
    arguments = parser.parse_args()
    if arguments.command == "refit":
        run_refit()
    elif arguments.artifact is None:
        parser.error("evaluate requires --artifact")
    else:
        run_evaluation(arguments.artifact)
