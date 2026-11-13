# Planned Architecture

## High-level pipeline

```text
NYC TLC monthly Parquet
  -> Python ingestion
  -> PostgreSQL RAW
  -> dbt staging and data-quality classification
  -> dimensional warehouse
  -> data marts
  -> OLAP, dashboard, and DSS
```

## Responsibilities

### Python

- Download source files
- Validate source files and schemas
- Calculate checksums
- Record ingestion metadata
- Enforce monthly idempotency
- Load source records into the PostgreSQL RAW layer

### dbt

- Create the staging layer
- Apply canonical names and types
- Classify records as valid, quarantined, or rejected
- Build dimensions and facts
- Build analytical and DSS marts

### Airflow

- Orchestrate pipeline steps only
- Invoke independently testable Python and dbt operations
- Avoid embedding data-processing or business logic in DAG files
- The optional Compose profile runs Airflow standalone locally.
- `yellow_taxi_ingestion` orchestrates a selected 2024 month range through
  RAW, zone seed, staging, staging tests, and audit classification counts.

### DSS

- Forecast day-ahead taxi pickup demand
- Compare forecasts with a historical baseline
- Assign an interpretable demand level
- Produce a decision-support recommendation

### Dashboard

- Present analytical and OLAP views
- Present forecasts, demand levels, and recommendations

## Team integration gates

### Gate A: staging to warehouse

Person 1 provides `stg_yellow_trip_valid`, including stable canonical names,
types, source lineage, and reconciled data-quality classification. Person 2
builds dimensions and facts from this interface rather than querying RAW.

### Gate B: warehouse to DSS

Person 2 provides sparse `mart_zone_hour_demand` at date x hour x pickup-zone
grain, monthly `mart_demand_coverage`, and a recommendation-eligibility flag.
Person 3 builds forecasting features and recommendations from those interfaces
rather than querying `fact_trip` directly.

PostgreSQL and the optional Airflow service run through Docker Compose.
Airflow metadata uses its own local-development volume, separate from trip
data. Warehouse/DSS/dashboard deployment remains to be finalized.
