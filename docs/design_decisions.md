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
| Ingestion concurrency | PostgreSQL session advisory lock per dataset and source month |
| Taxi Zone Lookup | Version-controlled dbt seed named `taxi_zone_lookup` |
| Staging materialization | `stg_yellow_trip` table and `stg_yellow_trip_valid` view |
| Excessive trip duration | Quarantine durations over 180 minutes |
| Source-month consistency | Quarantine pickup timestamps outside their source month |

The dimension and fact models use the `dw` schema; the demand mart is a table
in `mart`. The Person 2 analytical Overview and OLAP views now read that mart
through a repository layer. Current implementation (30 October 2026) includes
RF model selection, Q1 refit, April evaluation, historical forecast publication
and an integrated Overview/OLAP/Forecast dashboard. Selection versus actual-fit
metadata and the current demand-level policy are documented in
`docs/dss_refit_publication_runbook.md`; April evidence is in
`docs/dss_april_evaluation.md`. Further full-year loading/cloud deployment are
optional extensions. The Gate A formal-review status below is unchanged.

## Implemented RAW-load transaction boundary

The loader uses three transaction phases:

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
| Numeric edge handling | Classify RAW values before guarded canonical casts |
| DQ representation | `dq_status` plus zero or more `dq_reason_codes` |
| Taxi Zone Lookup | Shared reference contract used by staging and `dim_taxi_zone` |
| Same checksum rerun | Skip a previously successful month |
| Changed checksum | Fail until an explicit month replacement is requested |
| Person 1 boundary | Source file through `stg_yellow_trip_valid` |
| Person 2 boundary | Dimensions, `fact_trip`, marts, and OLAP |

Still intentionally unresolved for later milestones:

- Upper data-quality bound for distance
- Transactional implementation of `replace-month`
- Physical partitioning and indexing

The warehouse dimension key and unknown-member policies, including the
minute-level `dim_time`, are now recorded in `docs/dimensional_model.md`.
The demand mart uses observed date-hour-zone combinations and leaves dense
zero filling to Person 3; its provisional Gate B interface is in
`docs/gate_b_handoff.md`.
