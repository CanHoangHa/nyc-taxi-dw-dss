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

### DSS

- Forecast day-ahead taxi pickup demand
- Compare forecasts with a historical baseline
- Assign an interpretable demand level
- Produce a decision-support recommendation

### Dashboard

- Present analytical and OLAP views
- Present forecasts, demand levels, and recommendations

Implementation details, deployment topology, and service configuration remain
TBD.
