# Approved Design Decisions

The following decisions are frozen for the initial project scope:

| Area | Approved decision |
|---|---|
| Dataset | NYC TLC Yellow Taxi Trip Records for 2024 |
| Source organization | Monthly Parquet files |
| Reference data | NYC Taxi Zone Lookup |
| Batch grain | One source month per ingestion batch |
| Fact grain | One valid Yellow Taxi trip per `fact_trip` row |
| Forecast horizon | Day-ahead |
| Forecast grain | Date × hour × pickup zone |
| Forecast target | `trip_count` |
| Airflow responsibility | Orchestration only |
| Main DSS mart | `mart_zone_hour_demand` |
| Zone modeling | One role-playing `dim_taxi_zone` for pickup and drop-off |
| Data-quality states | Valid, quarantined, and rejected |
| January source schema | All 19 contract fields confirmed; exact types linked from the source profile |
| Unexpected source columns | Fail source validation until the contract is explicitly reviewed |
| RAW payload naming | Preserve exact TLC source names; dbt owns canonical names |
| RAW source identity | Dataset + source year + source month + zero-based source row number |
| Audit reconciliation | A succeeded batch requires source count = loaded count |
| RAW loading | Stream PyArrow RecordBatches through Psycopg COPY |

Staging and warehouse schemas, data-quality thresholds, model choice, forecast
thresholds, infrastructure configuration, and dashboard layout remain
intentionally TBD.

## Planned RAW-load transaction boundary

The loader milestone will use three short transaction phases:

1. Insert and commit the `started` audit attempt.
2. Load the complete RAW month and update that attempt to `succeeded` in one
   transaction.
3. If loading fails, roll back phase 2 before updating the committed audit
   attempt to `failed` in a separate transaction.

This keeps failure history while preventing a partially loaded RAW batch from
becoming visible.

## Gate A contract decisions proposed for team approval

The following decisions belong to contract draft `gate-a-v1-draft`. They become
frozen after Person 2 reviews the warehouse-consumer impact:

| Area | Proposed decision |
|---|---|
| Warehouse handoff | `stg_yellow_trip_valid` |
| Handoff grain | One normalized record classified as valid |
| Source-row identity | Dataset + source year + source month + source row number |
| Duplicate policy | Do not deduplicate using trip business fields |
| Timestamp storage | `timestamp without time zone`, interpreted as `America/New_York` |
| Monetary contract | Consumer-facing amounts use `numeric(12,2)` |
| DQ representation | `dq_status` plus zero or more `dq_reason_codes` |
| Taxi Zone Lookup | Shared reference contract used by staging and `dim_taxi_zone` |
| Same checksum rerun | Skip a previously successful month |
| Changed checksum | Fail until an explicit month replacement is requested |
| Person 1 boundary | Source file through `stg_yellow_trip_valid` |
| Person 2 boundary | Dimensions, `fact_trip`, marts, and OLAP |

Still intentionally unresolved for later milestones:

- Upper data-quality bounds for duration and distance
- Physical materialization of staging models
- Transactional implementation of `replace-month`
- Warehouse surrogate-key and unknown-member policies
- Physical partitioning and indexing
