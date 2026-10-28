"""Read-only checks of a published historical forecast against frozen outputs."""
import argparse
from datetime import date
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from psycopg.rows import dict_row

from dss.models import actual_fit_window, load_publication_artifact
from dss.persistence import ForecastRepository, validate_forecasts
from dss.ranking import rank_zone_interval
from taxi_dw.db import open_connection


def verify(artifact_path, forecast_date, predictions_path):
    artifact, digest = load_publication_artifact(artifact_path)
    report = json.loads((predictions_path.parent / "report.json").read_text(encoding="utf-8"))
    if (report["artifact_sha256"] != digest or report["files_sha256"][predictions_path.name]
            != hashlib.sha256(predictions_path.read_bytes()).hexdigest()):
        raise ValueError("offline report/artifact/predictions checksums disagree")
    offline = pd.read_parquet(predictions_path)
    offline = offline.loc[pd.to_datetime(offline.demand_date).eq(pd.Timestamp(forecast_date))]
    with open_connection() as connection:
        repository = ForecastRepository(connection)
        run = repository.latest_run(forecast_date)
        if run is None or run["artifact_sha256"] != digest:
            raise ValueError("dashboard latest run is not the requested artifact")
        fit_start, fit_end, kind = actual_fit_window(artifact)
        if (run["fit_start_date"], run["fit_end_date"], run["fit_kind"]) != (fit_start, fit_end, kind):
            raise ValueError("published actual fit metadata disagrees with artifact")
        if run["metrics_json"]["selection_validation"] != artifact.validation_metrics:
            raise ValueError("selection metrics were changed")
        rows = validate_forecasts(repository.read_forecasts(run["run_id"], forecast_date=forecast_date))
        sql_count, sql_grain, sql_zones, sql_invalid = connection.execute(
            "SELECT count(*), count(DISTINCT (forecast_date,demand_hour,pickup_zone_key)), "
            "count(DISTINCT pickup_zone_key), count(*) FILTER (WHERE EXISTS ("
            "SELECT 1 FROM unnest(ARRAY[predicted_trip_count,baseline_trip_count,"
            "historical_p50,historical_p75,demand_ratio]) AS value "
            "WHERE NOT (value >= 0 AND value < 'Infinity'::float8))) "
            "FROM dss.zone_hour_forecast WHERE run_id=%s AND forecast_date=%s",
            (run["run_id"], forecast_date)).fetchone()
        if (sql_count, sql_grain, sql_zones, sql_invalid) != (6312, 6312, 263, 0):
            raise ValueError("SQL count/grain/zone/finite-measure checks failed")
        reference = repository.ranking_zones()
        expected_ids = set(reference.loc[reference.is_actionable, "pickup_location_id"])
        if len(rows) != 6312 or set(rows.pickup_location_id) != expected_ids:
            raise ValueError("expected all 263 eligible zones and 6312 unique zone-hours")
        aligned = rows.merge(offline, on=["demand_hour", "pickup_zone_key"],
                             suffixes=("", "_offline"), validate="one_to_one")
        if len(aligned) != len(rows) or len(offline) != len(rows):
            raise ValueError("offline and published grains differ")
        np.testing.assert_allclose(aligned.predicted_trip_count, aligned.prediction_rf,
                                   rtol=1e-12, atol=1e-10)
        np.testing.assert_array_equal(aligned.baseline_trip_count, aligned.prediction_seasonal_naive)
        checked = []
        for borough in sorted(reference.loc[reference.is_actionable, "borough"].unique()):
            for start, end in ((8, 9), (6, 10)):
                ranking = rank_zone_interval(rows, borough=borough, start_hour=start,
                                             end_hour=end, zone_reference=reference)
                with connection.cursor(row_factory=dict_row) as cursor:
                    cursor.execute(
                        "SELECT pickup_location_id, sum(predicted_trip_count) AS predicted_trip_count, "
                        "sum(baseline_trip_count) AS baseline_trip_count FROM dss.zone_hour_forecast "
                        "WHERE run_id=%s AND forecast_date=%s AND borough=%s AND is_actionable "
                        "AND demand_hour >= %s AND demand_hour < %s GROUP BY pickup_location_id "
                        "ORDER BY pickup_location_id", (run["run_id"], forecast_date, borough, start, end))
                    sql = pd.DataFrame(cursor.fetchall())
                columns = ["pickup_location_id", "predicted_trip_count", "baseline_trip_count"]
                pd.testing.assert_frame_equal(
                    ranking[columns].sort_values("pickup_location_id").reset_index(drop=True), sql,
                    check_dtype=False, check_exact=False, rtol=1e-12, atol=1e-10)
                checked.append({"borough": borough, "interval": [start, end], "zones": len(ranking)})
        return {"run_id": str(run["run_id"]), "rows": len(rows), "zones": len(expected_ids),
                "max_absolute_offline_difference": float(np.max(np.abs(aligned.predicted_trip_count - aligned.prediction_rf))),
                "sql_count_grain_zones_invalid": [sql_count, sql_grain, sql_zones, sql_invalid],
                "sql_ranking_checks": checked, "artifact_sha256": digest}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--date", type=date.fromisoformat, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.artifact, args.date, args.predictions), indent=2))
