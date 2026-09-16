# NYC Taxi Data Warehouse & Decision Support System

## Status

The ingestion contract, local PostgreSQL infrastructure, idempotent
transactional RAW ingestion, safe monthly source downloader, strict validator,
and reproducible January 2024 source profiler are implemented. The source
Parquet and loaded PostgreSQL data remain local; no dbt model, Airflow DAG,
forecasting model, or dashboard has been implemented yet.

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
src/dbt/              Planned dbt project files
src/dss/              Planned forecasting and recommendation components
src/dashboard/        Planned Streamlit application
sql/                  Database bootstrap and ingestion-table DDL
data/sample/          Small, Git-safe samples only
data/reference/       Small reference datasets
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

No Airflow, dbt, ingestion, DSS, or dashboard service is included in Compose at
this milestone.

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
  --zone-lookup data/reference/taxi_zone_lookup.csv `
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
