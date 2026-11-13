# Gate C handoff — DSS forecast and recommendation output

Current status (30 October 2026): Q1 model selection, fixed RF refit through
31 March, April evaluation and historical 1 April publication are complete.
January-April data are loaded locally. Migration `004_dss_actual_fit.sql`
separately records actual fit and original selection windows. See
[publication runbook](dss_refit_publication_runbook.md) and
[April evaluation](dss_april_evaluation.md) for current evidence and commands.

The original schema/persistence verification below was performed on PostgreSQL
16.15 on 9 October 2026; its test counts describe that earlier milestone.

## Published tables

`sql/003_create_dss_tables.sql` creates:

- `dss.model_run`: immutable model, feature, recommendation, split, metric,
  Git SHA, and creation metadata.
- `dss.zone_hour_forecast`: one row per run × forecast date × local hour ×
  pickup zone, including prediction, baseline, p50/p75, ratio, level,
  recommendation, explanation, and actionability.

A model run and all of its forecast rows are inserted in one transaction.
Failure during row insertion rolls the metadata insert back. Old runs are not
overwritten; the dashboard reads the newest run containing the selected date.

## Bootstrap or migrate

For a new empty PostgreSQL volume, Docker executes numbered SQL automatically.
For an existing volume:

```powershell
docker compose exec -T postgres psql -v ON_ERROR_STOP=1 `
  -U nyc_taxi -d nyc_taxi_dw `
  -f /docker-entrypoint-initdb.d/003_create_dss_tables.sql
```

Use the credentials configured in `.env` if they differ from the example.

## Reproducible Q1 workflow

```powershell
$env:PYTHONPATH = (Resolve-Path "src").Path

python -m dss.pipeline build-dataset `
  --start-date 2024-01-01 --end-date 2024-03-31 `
  --output artifacts/dss_q1_dense.parquet

python -m dss.pipeline train --config configs/dss_q1.toml

python -m dss.pipeline evaluate `
  --config configs/dss_q1.toml `
  --artifact artifacts/models/<artifact-from-train>.joblib

python -m dss.pipeline forecast `
  --artifact artifacts/models/<artifact-from-train>.joblib `
  --date 2024-04-01
```

`train` prints the immutable artifact path, validation metrics for the model
and both baselines, and the selected approach. `evaluate` prints test metrics.
`forecast` prints the persisted run UUID and exact row count. Forecasting
2024-04-01 is allowed only if all 28 historical days through 2024-03-31 remain
covered by Gate B.

## Dashboard

Start Streamlit as before and choose **Dự báo & khuyến nghị**. The view shows:

- Total predicted pickups and count of High zone-hours.
- Model, feature, and recommendation versions.
- Prediction versus historical baseline by hour.
- Ranked zones, top-zone comparisons and an optional zone/hour heatmap.
- Collapsed hourly details, priority rules and model provenance.
- Date, borough, and local-hour filters.

No model is fit inside Streamlit. The UI remains a read-only consumer of Gate
C, with repository and service logic outside widget code.

Recommendation version **1.2.0** assigns High to positive prediction at or
above the train-only p75 of the same zone-hour, Medium to positive prediction
at or above p50 (unless High), and Low otherwise. Non-actionable zones remain
Not applicable. `baseline_trip_count` stays the D−7 seasonal-naive value;
`demand_ratio` reports weekly change separately from demand level. Thus seasonal
naive can indicate stable High demand with ratio 1; growth from a low base is
not sufficient for High. Zero predictions remain Low even with zero quantiles.
Existing saved runs retain their original policy version and values.

Forecast dates must be after both the artifact's validation end and actual fit
end (when refitted). Evaluation rejects
configs whose split differs from the artifact's saved experiment boundaries.
Historical train/validation observations remain valid lag/rolling inputs.

## Validation evidence and limitation

The DSS unit suite covers Gate B contracts, dense reconciliation, leakage,
calendar gaps, temporal split ordering, two baselines, non-negative model
output, metrics, recommendation boundaries, Gate C shape, transaction rollback,
service filtering, and an in-memory train/evaluate/forecast vertical slice.

The database integration suite passed **14/14** applicable Person 1 tests, with
three analytics tests skipped because the fresh volume had no dbt mart. The
Gate C integration test separately inserted one model run and 24 hourly rows,
read them through `ForecastRepository`, and used an outer rollback to verify
that no test run remained. The initialized database exposed both Gate C tables
and their constraints.

The checked-in Q1 config preserves the original selection experiment. March
test results have already been examined and are retrospective. The fixed-model
April evaluation is the current new-month evidence; it is not a full-year
claim. Further data and a newly frozen evaluation protocol are needed before
making broader seasonal/generalization claims. See `docs/dss_april_protocol.md`.
