# NYC Taxi Data Warehouse & Decision Support System

## Status

The ingestion contract and minimal local PostgreSQL infrastructure are under
development. No dataset has been downloaded, and no ingestion pipeline, dbt
model, Airflow DAG, forecasting model, or dashboard has been implemented yet.

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
src/taxi_dw/          Planned Python ingestion and shared modules
src/airflow/dags/     Planned Airflow DAG definitions
src/dbt/              Planned dbt project files
src/dss/              Planned forecasting and recommendation components
src/dashboard/        Planned Streamlit application
sql/                  Planned database bootstrap SQL
data/sample/          Small, Git-safe samples only
data/reference/       Small reference datasets
tests/                Planned automated tests
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

The database port is bound to localhost only.

The first initialization creates the `audit`, `raw`, `staging`, `dw`, and
`mart` schemas from `sql/001_create_schemas.sql`. PostgreSQL initialization
scripts run only for a new empty database volume.

Stop the service without deleting its named volume:

```powershell
docker compose down
```

No Airflow, dbt, ingestion, DSS, or dashboard service is included in Compose at
this milestone.
