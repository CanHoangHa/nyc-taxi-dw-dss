# NYC Taxi Data Warehouse & Decision Support System

## Status

Planning and repository setup only. No ingestion pipeline, database, dbt model,
Airflow DAG, forecasting model, or dashboard has been implemented yet.

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
