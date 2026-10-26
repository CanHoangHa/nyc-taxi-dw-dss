# Local Airflow Runbook

## Runtime

Airflow 3.3.2 runs in one optional Docker Compose service using `airflow
standalone`. This starts the scheduler, DAG processor, API/UI, and triggerer
for local development. Airflow metadata and task logs persist in the
`airflow_data` volume, separate from the PostgreSQL `postgres_data` volume.
Standalone uses SQLite for its metadata; trip data stays in PostgreSQL.

The scheduler health threshold is 120 seconds for this local runtime.
Docker health checks inspect the reported database and component statuses,
not just the HTTP response code.

Project Python/dbt packages live in `/home/airflow/taxi-venv`, isolated from
Airflow's dependencies. Source code is mounted read-only. dbt logs and target
files go into the Airflow volume; cached Parquet files use `data/raw` on the
host and remain outside Git.

This runtime is for the local university demo. Its UI is bound to loopback
and configured to allow local access as admin without a login. Public hosting
requires a different authentication and deployment setup.

## Start

Configure `.env` using `.env.example`, then run from the repository root:

```powershell
docker compose --profile airflow up -d --build
docker compose --profile airflow ps
```

Open `http://localhost:8080`. Set `AIRFLOW_PORT` in `.env` if port 8080 is in
use. The image build is only needed initially or after requirements/Dockerfile
changes. Regular startup can omit `--build`.

The optional profile keeps `docker compose up -d postgres` unchanged.

## Trigger the pipeline

Find and unpause `yellow_taxi_ingestion` in the UI, then select Trigger.
The default parameters load January-March 2024:

```json
{"year": 2024, "start_month": 1, "end_month": 3}
```

Use the same start/end month for a single month. The year is restricted to
2024, and months must be 1-12. A reversed range fails in ingestion before
download or database writes. Only one run executes at a time because staging
is a full-dataset rebuild.

The DAG is manually triggered (`schedule=None`, `catchup=False`). It does
not automatically ingest the current calendar month, which would be outside
the historical 2024 scope.

```text
ingest_raw
  -> seed_lookup
  -> build_staging
  -> test_staging
  -> record_dq_counts
```

| Task | Existing operation |
|---|---|
| `ingest_raw` | Python `taxi_dw.ingestion backfill`: download, validate, append or skip |
| `seed_lookup` | dbt seed `taxi_zone_lookup` |
| `build_staging` | dbt run, selecting staging models |
| `test_staging` | dbt tests for staging, the RAW source, and the zone seed |
| `record_dq_counts` | Python `taxi_dw.staging_audit`: reconcile and update audit |

A same-checksum ingestion skip exits successfully, so staging, tests, and
audit refresh still execute. Each task retries once after 30 seconds and
has a 30-minute timeout. Inspect each task's log in the UI to find failures.

Test selection uses `--indirect-selection cautious`, so tests involving
warehouse models outside this DAG are left to the warehouse workflow.

## Audit write-back

The final task validates the complete loaded snapshot by batch:

```text
source rows = loaded rows = physical RAW rows = staging rows
staging rows = valid + quarantined + rejected
```

Only after all batches reconcile does it write classification counts to
their `succeeded` audit records in one transaction. `skipped` attempts loaded
zero new rows and keep their DQ counts null. All loaded months are refreshed
because dbt rebuilds all of staging, even when the requested range is narrow.

`status=succeeded` in `audit.etl_batch` continues to describe the RAW load.
An Airflow/dbt failure is visible in the DAG's task/run status; it does not
rewrite a previously successful RAW load as failed.

You can run this module without Airflow after dbt tests pass:

```powershell
$env:PYTHONPATH = (Resolve-Path "src").Path
.\.venv\Scripts\python.exe -m taxi_dw.staging_audit
```

Inspect counts:

```powershell
docker compose exec -T postgres psql -U nyc_taxi -d nyc_taxi_dw `
  -c "SELECT source_month, status, loaded_row_count, valid_count, quarantined_count, rejected_count FROM audit.etl_batch ORDER BY started_at;"
```

## Tests and recovery

Project tests, including the isolated audit database integration tests:

```powershell
$env:PYTHONPATH = (Resolve-Path "src").Path
$env:RUN_DB_TESTS = "1"
.\.venv\Scripts\python.exe -m unittest discover -s tests -t . -v
```

DAG tests run with Airflow's Python inside its container:

```powershell
docker compose exec -T airflow python /opt/project/src/airflow/tests/test_dag.py
docker compose exec -T airflow airflow dags list-import-errors
```

If a task fails, fix its logged cause and clear that task and downstream
tasks in the UI, or trigger the same month range again. Completed RAW months
are skipped on retry. Changed source checksums still fail safely;
`replace-month` is not implemented.

Run CLI ingestion/dbt separately when no DAG is executing. If RAW changes
between staging and audit refresh, reconciliation can fail and the snapshot
must be rebuilt and tested before write-back.

Stop local services while retaining both data volumes:

```powershell
docker compose --profile airflow down
```

## Verification - 2026-10-08

- DAG run: `verify_q1_20261008_stable`, final state `success`.
- All five tasks succeeded on their first attempt in the final run.
- January-March ingestion was skipped with no new RAW rows.
- Staging rebuilt all 9,554,778 rows.
- dbt tests: 24 passed (23 data tests and 1 unit test), using cautious selection.
- Project Python/PostgreSQL tests: 55 passed. Airflow DAG tests: 3 passed.
- Airflow and PostgreSQL services were healthy after the run.

The final audit task populated these counts on the three original successful
RAW batches; every row reconciles to its loaded count:

| Source month | Loaded | Valid | Quarantined | Rejected |
|---|---:|---:|---:|---:|
| 2024-01 | 2,964,624 | 2,924,187 | 40,381 | 56 |
| 2024-02 | 3,007,526 | 2,964,028 | 43,491 | 7 |
| 2024-03 | 3,582,628 | 3,520,696 | 61,815 | 117 |

Skipped attempts retained null DQ counts. The full scheduled execution took
about 13 minutes on this development machine, including a full staging rebuild;
this is an observation rather than a runtime guarantee.

An earlier smoke run was interrupted during scheduler heartbeat delays and
Docker engine disruption. The final run was performed after applying the
120-second scheduler health threshold and the component-aware health probe.
The earlier failed run remains visible in Airflow's history.

## References

- [Airflow standalone quick start](https://airflow.apache.org/docs/apache-airflow/3.3.2/start.html)
- [Isolated Python environments in the Airflow image](https://airflow.apache.org/docs/docker-stack/build.html)
- [Airflow component health checks](https://airflow.apache.org/docs/apache-airflow/3.3.2/administration-and-deployment/logging-monitoring/check-health.html)
