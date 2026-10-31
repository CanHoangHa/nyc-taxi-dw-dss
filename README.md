# NYC Taxi Data Warehouse & Decision Support System

## Status

The ingestion contract, local PostgreSQL infrastructure, idempotent
transactional RAW ingestion, safe monthly source downloader, strict validator,
reproducible January 2024 source profiler, ordered month-range backfill, and
dbt staging layer are implemented. A local Airflow DAG orchestrates the
pipeline through tested staging and audit DQ-count write-back.
Five warehouse dimensions and `fact_trip` are implemented in `dw`, and
`mart_zone_hour_demand` and `mart_demand_coverage` are implemented in `mart`.
The analytical Overview/OLAP views and the Person 3 day-ahead DSS pipeline,
versioned Gate C output, and forecast/recommendation view are implemented. The
source Parquet, model artifacts, and loaded PostgreSQL data remain local.

As of 31 October 2026, the verified local prototype contains January–April
2024. Random Forest was selected on Q1 validation, refitted through 31 March,
evaluated on April, and published for the historical 1–30 April demo. The
dashboard includes chart drill-down, weekday/hour averages, zone ranking and
forecast comparisons. See [April results](docs/dss_april_evaluation.md) and
[publication runbook](docs/dss_refit_publication_runbook.md).

## Open an already prepared local demo

With Docker Desktop running, the existing database loaded, and `.venv`/`.env`
configured, run from the repository root:

```powershell
docker compose up -d postgres
.\.venv\Scripts\python.exe -m streamlit run src/dashboard/app.py
```

Open the URL printed by Streamlit (normally <http://localhost:8501>). The
development preview may instead be running at <http://127.0.0.1:8502>.
Airflow and retraining are not required to view existing data and forecasts.
Cloning the repository alone does not supply the database or model artifacts;
use the setup/data-build steps below for a fresh environment.

## Objective

Build a university-scale data warehouse from NYC TLC Yellow Taxi Trip Records
for 2024 and a decision support system that forecasts day-ahead pickup
demand by date, hour, and taxi zone.

The intended decision is where and when taxi availability should be prioritized.

## Stack

- Python
- PostgreSQL
- dbt Core
- Apache Airflow (optional local orchestration)
- Streamlit
- scikit-learn
- Docker Compose
- Git

## Intended architecture

```text
NYC TLC monthly Parquet
  -> Python ingestion
  -> PostgreSQL RAW
  -> dbt staging and data quality
  -> dimensional warehouse
  -> data marts
  -> OLAP, dashboard, and DSS
```

Airflow orchestrates ingestion through tested staging and audit write-back.
Warehouse/mart builds currently run through the documented dbt commands.
Business and data-processing logic lives outside DAG definitions.

## Repository structure

```text
src/taxi_dw/          Python ingestion and shared modules
src/airflow/dags/     Airflow ingestion/staging DAG
src/dbt/              dbt staging, warehouse, mart, seed, and data tests
src/dss/              Forecasting, evaluation, recommendation, and Gate C modules
src/dashboard/        Overview, OLAP, and DSS Streamlit application
sql/                  Database bootstrap, ingestion, and Gate C DDL
data/sample/          Small, Git-safe samples only
tests/                Unit and PostgreSQL integration tests
docs/                 Architecture and design documentation
```

The frozen scope and planned interfaces are documented in `docs/`. Full raw
NYC TLC data must not be committed to this repository.

## Local PostgreSQL setup

Prerequisites:

- Docker with Docker Compose v2
- Python 3.11 or later for project modules (local verification uses Python 3.11)

Create a local environment file:

```powershell
Copy-Item .env.example .env
```

Change the example password in `.env`, then validate and start PostgreSQL:

```powershell
docker compose config
docker compose up -d postgres
docker compose ps
```

Python settings also load `.env` automatically for local development. Existing
process environment variables take precedence, so Docker, Airflow, and CI can
inject configuration without being overwritten by the local file.

The database port is bound to localhost only.

The first initialization runs all numbered scripts under `sql/`, including the
ingestion tables and the `dss` Gate C tables. PostgreSQL initialization scripts
run only for a new empty database volume.

For an existing local volume created before a new SQL script was added, apply
that script explicitly:

```powershell
docker compose exec -T postgres psql -v ON_ERROR_STOP=1 `
  -U nyc_taxi -d nyc_taxi_dw `
  -f /docker-entrypoint-initdb.d/002_create_ingestion_tables.sql
```

Apply `003_create_dss_tables.sql` the same way before publishing forecasts to
an existing volume. If the DSS tables already exist, apply the idempotent
actual-fit metadata migration before publishing refitted models:

```powershell
docker compose exec -T postgres psql -v ON_ERROR_STOP=1 `
  -U nyc_taxi -d nyc_taxi_dw `
  -f /docker-entrypoint-initdb.d/004_dss_actual_fit.sql
```

Keep the existing volume; migrations do not require deleting or recreating it.

After the data-build steps below have created the warehouse/marts, run all
unit and database integration tests while PostgreSQL is healthy:

```powershell
$env:PYTHONPATH = (Resolve-Path "src").Path
$env:RUN_DB_TESTS = "1"
$env:RUN_ANALYTICS_TESTS = "1"
.\.venv\Scripts\python.exe -m unittest discover -s tests -t . -v
```

`RUN_DB_TESTS=1` enables pipeline/DSS database tests; `RUN_ANALYTICS_TESTS=1`
enables warehouse/analytics tests. Without these flags the corresponding tests
are skipped; unit tests still run normally. Run discovery from the repository root
with `-t .` so `tests/dss` does not shadow the `src/dss` package.

Stop the service without deleting its named volume:

```powershell
docker compose down
```

Compose includes an optional `airflow` profile. The local CLI/dbt workflow
also works independently. Start the Airflow UI and scheduler with:

```powershell
docker compose --profile airflow up -d --build
```

Open `http://localhost:8080`, unpause `yellow_taxi_ingestion`, and trigger the
desired 2024 month range. See `docs/airflow_runbook.md` for task flow, audit
semantics, tests, and recovery. The DAG stops after staging/audit; run the dbt
warehouse and mart commands below to refresh analytics after a new month.
DSS and dashboard services are not included in Compose.

The DAG defaults to January–March. Choosing one month limits RAW ingestion,
but staging/tests/audit still cover all loaded data. A matching successful
source checksum skips RAW loading; it does not skip the staging rebuild.
For a short presentation, prepare a completed DAG run and show its tasks/logs
alongside the preloaded dashboard instead of waiting for a full rebuild live.

## January 2024 source profile

Install project dependencies and place the official January Yellow Taxi
Parquet file at:

```text
data/raw/yellow/2024/01/yellow_tripdata_2024-01.parquet
```

Then run the bounded-memory profiler from the repository root:

```powershell
$env:PYTHONPATH = (Resolve-Path "src").Path
.\.venv\Scripts\python.exe -m taxi_dw.source_profile `
  --path data/raw/yellow/2024/01/yellow_tripdata_2024-01.parquet `
  --year 2024 `
  --month 1 `
  --zone-lookup src/dbt/seeds/taxi_zone_lookup.csv `
  --output docs/profiles/yellow_tripdata_2024_01.md
```

The generated report records the source checksum, physical schema, exact
counts and bounds, sampled quantiles, and initial data-quality indicators. The
Parquet artifact remains outside Git.

## Monthly source download

Download a 2024 Yellow Taxi source month from the official TLC location:

```powershell
$env:PYTHONPATH = (Resolve-Path "src").Path
.\.venv\Scripts\python.exe -m taxi_dw.downloader --year 2024 --month 1
```

The downloader streams to a `.part` file, calculates SHA-256 while writing,
and renames the file only after a complete response. Temporary connection and
server errors are retried; HTTP 404 is not. If the completed destination file
already exists, it is reused without an HTTP request or overwrite and its
checksum is calculated again.

Validate the downloaded artifact before database loading:

```powershell
.\.venv\Scripts\python.exe -m taxi_dw.source_validation `
  --year 2024 `
  --month 1
```

Validation recalculates the checksum, opens the Parquet footer, requires at
least one row, and compares field names and physical types with the frozen 2024
source contract. Missing, unexpected, incorrectly cased, or differently typed
fields fail with a specific message. Record-level anomalies remain staging
data-quality work and do not make the complete source artifact invalid.

## Ingestion runbook

From a fresh checkout, install dependencies and start PostgreSQL:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Change the example database password in `.env`, then start Compose:

```powershell
docker compose up -d postgres
docker compose ps
```

Run January end to end from download/reuse through validation and RAW:

```powershell
$env:PYTHONPATH = (Resolve-Path "src").Path
.\.venv\Scripts\python.exe -m taxi_dw.ingestion run `
  --dataset yellow_taxi `
  --year 2024 `
  --month 1 `
  --batch-size 10000
```

The loader streams PyArrow RecordBatches into PostgreSQL with Psycopg COPY. It
does not materialize the complete Parquet file in memory. A `started` audit row
is committed first; the RAW rows and `succeeded` update then commit together.
On failure, the RAW transaction is rolled back before the audit row is marked
`failed`.

The first local January run loaded 2,964,624 rows in 192.06 seconds end to end.
The database load transaction took 184.34 seconds, and the observed Python
process-tree peak working set was 176.75 MiB. These figures are development
observations, not performance guarantees.

Run the same command again to demonstrate idempotency. It exits successfully
with `status=skipped`, writes a skipped audit attempt, and leaves RAW unchanged.
Attempts for the same source month are serialized with a PostgreSQL advisory
lock, including across transaction commits.

### Backfill a range of months

Process an inclusive month range in ascending order using the same monthly
loader:

```powershell
$env:PYTHONPATH = (Resolve-Path "src").Path
.\.venv\Scripts\python.exe -m taxi_dw.ingestion backfill `
  --year 2024 --start-month 1 --end-month 3
```

Each month has its own transaction and audit attempt. Months with an identical
successful checksum are skipped, while new months are appended to RAW. The
command stops at the first failure and returns a nonzero exit code. Earlier
successful months remain loaded; rerunning the same range safely resumes by
skipping them. A reversed or out-of-scope range fails before downloading.

Backfill does not replace an existing source month. A changed checksum still
fails without modifying that month's RAW records. After loading a range, run
the dbt seed, staging models, and tests below. RAW ingestion is incremental by
month; the current staging table is rebuilt from all loaded RAW months.

Inspect the audit trail and RAW reconciliation:

```powershell
docker compose exec -T postgres psql -U nyc_taxi -d nyc_taxi_dw `
  -c "SELECT batch_id, source_year, source_month, status, source_row_count, loaded_row_count, error_message FROM audit.etl_batch ORDER BY started_at DESC;" `
  -c "SELECT batch_id, count(*), min(source_row_number), max(source_row_number) FROM raw.yellow_trip GROUP BY batch_id;"
```

Operational failures are handled as follows:

- Download or schema-validation failure exits nonzero before touching RAW.
- A COPY failure rolls back all RAW rows for that attempt and records `failed`.
- A successful month with a different checksum records `failed`, leaves RAW
  unchanged, and reports that `replace-month` is not implemented yet.
- Restore the reviewed official source file before retrying a checksum or
  schema mismatch; do not manually edit RAW or its audit history.

The CLI never prints the configured database password. Use `--help` or
`run --help` to inspect the supported interface.

## dbt staging

dbt reads connection settings from environment variables only. For local
development, `dotenv` loads the Git-ignored `.env` before each command:

```powershell
.\.venv\Scripts\dotenv.exe -f .env run -- .\.venv\Scripts\dbt.exe debug --project-dir src/dbt --profiles-dir src/dbt
.\.venv\Scripts\dotenv.exe -f .env run -- .\.venv\Scripts\dbt.exe seed --project-dir src/dbt --profiles-dir src/dbt
.\.venv\Scripts\dotenv.exe -f .env run -- .\.venv\Scripts\dbt.exe run --project-dir src/dbt --profiles-dir src/dbt --select staging
.\.venv\Scripts\dotenv.exe -f .env run -- .\.venv\Scripts\dbt.exe test --project-dir src/dbt --profiles-dir src/dbt --select staging source:raw taxi_zone_lookup --indirect-selection cautious
.\.venv\Scripts\python.exe -m taxi_dw.staging_audit
```

The seed creates `staging.taxi_zone_lookup`. The table
`staging.stg_yellow_trip` classifies every RAW row as `valid`, `quarantined`, or
`rejected`; the view `staging.stg_yellow_trip_valid` is the warehouse handoff.
January classification results are recorded in
`docs/profiles/yellow_tripdata_2024_01_dq.md`.

January-March source batches, append-only loading, rerun evidence, and
multi-month reconciliation are recorded in
`docs/profiles/yellow_tripdata_2024_q1_dq.md`.

The reproducible January reconciliation, idempotent-rerun evidence, known
limitations, and Person 2 review checklist are in `docs/gate_a_handoff.md`.

## dbt warehouse

After seeding, rebuild staging, the warehouse, and the demand mart, then test
the full project:

```powershell
.\.venv\Scripts\dotenv.exe -f .env run -- .\.venv\Scripts\dbt.exe run --project-dir src/dbt --profiles-dir src/dbt --select staging warehouse marts
.\.venv\Scripts\python.exe -m taxi_dw.staging_audit
.\.venv\Scripts\dotenv.exe -f .env run -- .\.venv\Scripts\dbt.exe test --project-dir src/dbt --profiles-dir src/dbt
```

The models create `dw.dim_date`, `dw.dim_time`, `dw.dim_taxi_zone`,
`dw.dim_vendor`, `dw.dim_payment_type`, and `dw.fact_trip`. A custom dbt schema
macro keeps the requested schema name exactly `dw` rather than `staging_dw`. Date and time
are based on New York local timestamps; the minute-level choice and key mapping
are documented in `docs/dimensional_model.md`. The column-level fact and
dimension dictionary is in `docs/warehouse_data_dictionary.md`. Full `dbt test` checks both
staging and warehouse contracts.

`fact_trip` contains exactly one row per valid staging trip and preserves the
source key and lineage. It uses both pickup and drop-off roles for date, minute,
and zone. Nullable source measures stay null. RAW money is `double precision`;
staging validates before rounding to bounded two-decimal numeric values, and
fact money columns explicitly use `numeric(12,2)`. Distance/duration stay
`double precision`. The mart groups valid pickups by
New York local date, hour, and taxi zone. It contains only combinations with at
least one pickup; see `docs/gate_b_handoff.md` for the zero-demand policy and
Person 3 handoff.
`mart.mart_demand_coverage` is a view that lists only months whose classified
audit count agrees with the fact and mart totals. The dimension and mart mark
TLC zones 1–263 as eligible for dispatch recommendations; zones 264/265 remain
in analytical totals. Person 3 builds the dense forecast grid from eligible
zones and covered months.

## Analytical and DSS dashboard

After PostgreSQL is running and the dbt warehouse/mart build above has passed,
start the Overview and OLAP application from the repository root:

```powershell
.\.venv\Scripts\python.exe -m streamlit run src/dashboard/app.py
```

Open the local URL printed by Streamlit. The English dashboard has three views:

- **Overview:** total valid pickups, average pickups per day, busiest hour,
  daily/hourly/borough charts and a Top 10/20/30 zone selector.
- **OLAP:** click month → day → hour or borough → zone, and use the back
  control beside each chart to roll up. The weekday/hour heatmap follows the
  current scope. Each cell averages that weekday's occurrences, including
  zero-pickup days; weekdays outside the date range are unavailable, not zero.
- **Forecast & priorities:** choose **Planning scope** (date, borough, shift
  hours, optional zones and a 5/10/20-zone shortlist), then press **Apply**.
  **Zones to review** appears first, followed by hourly/D−7 comparisons and
  the optional zone/hour heatmap. Shortlist length changes the display, not
  the forecast totals or the historical evaluation's fixed K.
  Model details, priority rules and historical evaluation are collapsed.

Overview/OLAP share **Pickup filters**. Choose dates, borough, hours and zones,
then press **Apply filters**; draft edits do not rerun the queries. Leaving
zones empty selects all zones in the borough. Historical hours include both
endpoints (6–9 means 06:00–09:59). Forecast has a separate submitted form and excludes
the end hour: [6,10) covers the same four hours. All hours use New York time.
SQL lives in `src/dashboard/analytics_repository.py`. Analytics read the mart
and coverage view; forecasts read persisted DSS runs, without training in the UI.

The mart is sparse and January-April 2024 are currently loaded. An absent
combination in a month listed by `mart.mart_demand_coverage` means zero
**valid** pickups; an unlisted month has unavailable data. Use **Reload data** after a dbt rebuild or wait
up to five minutes for the dashboard cache. Query definitions, four runnable
OLAP examples, field meanings, and reconciliation guidance are in
`docs/olap_analytics.md`. Choose **Forecast & priorities** after a Gate C
forecast is published to compare prediction with baseline and review ranked,
versioned recommendations. The 1–30 April 2024 forecasts are historical demos;
April actuals are already known. Pickup ranking does not calculate the number
of taxis to dispatch or unmet demand.

Local `.env.example` uses `POSTGRES_HOST=127.0.0.1` to avoid slow localhost
fallback on this Windows setup. Restart Streamlit after changing `.env`.
Initial coverage verification may take longer because it reconciles the fact
table; subsequent interactions use cached data. Do not rebuild the warehouse
just to refresh a chart.

Validate the analytics repository against the rebuilt local mart with:

```powershell
$env:PYTHONPATH = (Resolve-Path "src").Path
$env:RUN_ANALYTICS_TESTS = "1"
.\.venv\Scripts\python.exe -m unittest discover -s tests -t . -v
```

The analytics integration tests compare the dashboard totals and OLAP
roll-ups with `dw.fact_trip`, then verify filtered slice/dice counts. Existing
database integration tests remain controlled separately by `RUN_DB_TESTS=1`.

## Person 3 DSS workflow

Install the requirements, apply `sql/003_create_dss_tables.sql`, and keep the
Q1 mart current. From the repository root:

```powershell
$env:PYTHONPATH = (Resolve-Path "src").Path
.\.venv\Scripts\python.exe -m dss.pipeline train --config configs/dss_q1.toml
.\.venv\Scripts\python.exe -m dss.pipeline evaluate `
  --config configs/dss_q1.toml `
  --artifact artifacts/models/<artifact-from-train>.joblib
.\.venv\Scripts\python.exe -m dss.pipeline forecast `
  --artifact artifacts/models/<artifact-from-train>.joblib `
  --date 2024-04-01
```

Training compares Poisson gradient boosting and Random Forest with seasonal-naive
and same-weekday-median baselines on validation only. Evaluation opens the test
split after selection and requires the same split boundaries saved in the artifact.
The Q1 March test period has already been explored; rerunning it is retrospective,
not a fresh holdout. Forecast dates must be strictly after both actual fit end
and the artifact's validation end, since
validation was used to select the approach. Complete history through D−1
(including train/validation dates) remains valid input for lag/rolling features.
Forecasting requires complete Gate B coverage for the preceding 28 days and
persists one atomic 24 × eligible-zone run. Recommendation version 1.2.0 uses
positive prediction versus training p50/p75 for demand levels; the D−7 ratio
separately describes weekly change. Stable high demand can be High even when
seasonal naive is selected and the ratio equals 1. See
`docs/dss_design.md` and `docs/gate_c_handoff.md` for contracts, limitations,
and the complete runbook.

### Fixed Q1 refit, April evaluation and publication

The validation-selected RF can be refitted on all January 29–March 31 rows
without rerunning selection. Selection boundaries remain immutable; the new
artifact separately records its actual fit window. March is then fit data,
and evaluation uses April 1–30 with actual history only through each D−1.
The current schema supports separate selection/actual-fit metadata after
migration `004_dss_actual_fit.sql`. Artifacts remain local and immutable;
publication writes new forecast runs without overwriting older runs.

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
$env:OMP_NUM_THREADS = '2'
.\.venv\Scripts\python.exe scripts/evaluate_dss_april.py refit
.\.venv\Scripts\python.exe scripts/evaluate_dss_april.py evaluate --artifact artifacts/models/<refit-directory>/model.joblib
```

These experiment commands require the parent artifact documented in
`docs/dss_april_protocol.md`; artifacts/manifest files are not included in Git.
Use trusted local artifacts or a separately supplied artifact/manifest bundle.
Use the saved artifact to repeat evaluation without fitting again. To publish
an existing refit after migration:

```powershell
.\.venv\Scripts\python.exe -m dss.pipeline forecast `
  --artifact artifacts/models/<refit-directory>/model.joblib `
  --date 2024-04-01
```

See the [publication and verification runbook](docs/dss_refit_publication_runbook.md),
[the frozen protocol](docs/dss_april_protocol.md) and
[the April report](docs/dss_april_evaluation.md) for exact paths, data build
commands, regression metrics, paired ranking evaluation, and limitations.
