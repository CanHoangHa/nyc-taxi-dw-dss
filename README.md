# NYC Taxi Data Warehouse & Decision Support System

## Status

The ingestion contract, local PostgreSQL infrastructure, idempotent
transactional RAW ingestion, safe monthly source downloader, strict validator,
reproducible January 2024 source profiler, and dbt staging layer are implemented.
Five warehouse dimensions and `fact_trip` are implemented in `dw`, and
`mart_zone_hour_demand` is implemented in `mart`. The analytical Overview and
OLAP Streamlit views are implemented. Airflow, forecasting, and the DSS view
remain planned. The source Parquet and loaded PostgreSQL data remain local.

## Objective

Build a university-scale data warehouse from NYC TLC Yellow Taxi Trip Records
for 2024 and, later, a decision support system that forecasts day-ahead pickup
demand by date, hour, and taxi zone.

The intended decision is where and when taxi availability should be prioritized.

## Planned stack

- Python
- PostgreSQL
- dbt Core
- Apache Airflow
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

Airflow will orchestrate the pipeline only. Business and data-processing logic
will live outside DAG definitions.

## Repository structure

```text
src/taxi_dw/          Python ingestion and shared modules
src/airflow/dags/     Planned Airflow DAG definitions
src/dbt/              dbt staging, warehouse, mart, seed, and data tests
src/dss/              Planned forecasting and recommendation components
src/dashboard/        Overview and OLAP Streamlit application
sql/                  Database bootstrap and ingestion-table DDL
data/sample/          Small, Git-safe samples only
tests/                Unit and PostgreSQL integration tests
docs/                 Architecture and design documentation
```

The frozen scope and planned interfaces are documented in `docs/`. Full raw
NYC TLC data must not be committed to this repository.

## Local PostgreSQL setup

Prerequisites:

- Docker with Docker Compose v2
- Python 3.10 or later for project modules

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

The first initialization creates the `audit`, `raw`, `staging`, `dw`, and
`mart` schemas, then creates `audit.etl_batch` and `raw.yellow_trip` from the
numbered scripts under `sql/`. PostgreSQL initialization scripts run only for a
new empty database volume.

For an existing local volume created before a new SQL script was added, apply
that script explicitly:

```powershell
docker compose exec -T postgres psql -v ON_ERROR_STOP=1 `
  -U nyc_taxi -d nyc_taxi_dw `
  -f /docker-entrypoint-initdb.d/002_create_ingestion_tables.sql
```

Run all unit and database integration tests while PostgreSQL is healthy:

```powershell
$env:PYTHONPATH = (Resolve-Path "src").Path
$env:RUN_DB_TESTS = "1"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Without `RUN_DB_TESTS=1`, database integration tests are discovered and
skipped; unit tests still run normally.

Stop the service without deleting its named volume:

```powershell
docker compose down
```

No Airflow, ingestion, DSS, or dashboard service is included in Compose. dbt is
run locally and connects to the PostgreSQL service.

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
.\.venv\Scripts\dotenv.exe -f .env run -- .\.venv\Scripts\dbt.exe test --project-dir src/dbt --profiles-dir src/dbt
```

The seed creates `staging.taxi_zone_lookup`. The table
`staging.stg_yellow_trip` classifies every RAW row as `valid`, `quarantined`, or
`rejected`; the view `staging.stg_yellow_trip_valid` is the warehouse handoff.
January classification results are recorded in
`docs/profiles/yellow_tripdata_2024_01_dq.md`.

The reproducible January reconciliation, idempotent-rerun evidence, known
limitations, and Person 2 review checklist are in `docs/gate_a_handoff.md`.

## dbt warehouse

After seeding, rebuild staging, the warehouse, and the demand mart, then test
the full project:

```powershell
.\.venv\Scripts\dotenv.exe -f .env run -- .\.venv\Scripts\dbt.exe run --project-dir src/dbt --profiles-dir src/dbt --select staging warehouse marts
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
and zone. Nullable source measures stay null. The mart groups valid pickups by
New York local date, hour, and taxi zone. It contains only combinations with at
least one pickup; see `docs/gate_b_handoff.md` for the zero-demand policy and
Person 3 handoff.

## Analytical dashboard (Person 2)

After PostgreSQL is running and the dbt warehouse/mart build above has passed,
start the Overview and OLAP application from the repository root:

```powershell
.\.venv\Scripts\streamlit.exe run src/dashboard/app.py
```

Open the local URL printed by Streamlit. The sidebar filters pickup dates,
borough, local pickup hours, and optional TLC taxi zones. Overview displays
pickup-trip KPIs and daily/hourly/geographic charts. OLAP switches between
month, day, day-hour, borough, and zone groupings; the filters implement
slice/dice. SQL lives in `src/dashboard/analytics_repository.py`, not in the
view. The app reads `mart.mart_zone_hour_demand` and does not read RAW.

The mart is sparse and currently only January 2024 is loaded. An absent
combination in a fully built month means zero **valid** pickups; an unloaded
month has unavailable data. Use the refresh button after a dbt rebuild or wait
up to five minutes for the dashboard cache. Query definitions, four runnable
OLAP examples, field meanings, and reconciliation guidance are in
`docs/olap_analytics.md`. The DSS recommendation page belongs to Person 3 and
can be integrated when Gate C is ready.

Validate the analytics repository against the rebuilt local mart with:

```powershell
$env:PYTHONPATH = (Resolve-Path "src").Path
$env:RUN_ANALYTICS_TESTS = "1"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The analytics integration tests compare the dashboard totals and OLAP
roll-ups with `dw.fact_trip`, then verify filtered slice/dice counts. Existing
database integration tests remain controlled separately by `RUN_DB_TESTS=1`.
