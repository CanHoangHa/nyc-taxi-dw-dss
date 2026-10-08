# NYC Taxi DW/DSS Project Plan

## 1. Purpose and status

This document is the shared implementation plan for the three-person team. It
defines the frozen scope, responsibility boundaries, dependency order,
milestones, handoff contracts, and acceptance criteria.

Implementation status (4 October 2026): local PostgreSQL, January 2024 RAW
ingestion and dbt staging, the five dimensions, `fact_trip`, the zone-hour
demand mart, and the analytical Overview/OLAP views are implemented. The
warehouse and mart rebuild and all 88 dbt tests pass on January data. Gate B
awaits Person 3 consumer review. Incremental multi-month ingestion, Airflow,
forecasting, the DSS view, and final integration remain open.

## 2. Frozen project scope

### Business goal

Build a university-scale data warehouse and decision support system that helps
an operator answer:

> Where and when will NYC Yellow Taxi pickup demand be high tomorrow?

The DSS will eventually recommend where taxi availability should be prioritized.
It will not claim to estimate unmet demand, optimize routes, or calculate profit.

### Data scope

- NYC TLC Yellow Taxi Trip Records for 2024
- Monthly Parquet source files
- NYC Taxi Zone Lookup as reference data
- January 2024 for the first vertical slice
- January-March 2024 for the incremental-ingestion prototype
- Full year 2024 only after the vertical slice and incremental pipeline are stable

Full raw trip files must not be committed to Git.

### Warehouse and DSS scope

- `fact_trip` grain: one valid Yellow Taxi trip
- Planned dimensions:
  - `dim_date`
  - `dim_time`
  - `dim_taxi_zone`
  - `dim_vendor`
  - `dim_payment_type`
- `dim_taxi_zone` is role-playing for pickup and drop-off
- Main DSS mart: `mart_zone_hour_demand`
- Forecast grain: date x hour x pickup zone
- Forecast target: `trip_count`
- Forecast horizon: day-ahead
- Data-quality states: valid, quarantined, rejected

### Technology scope

- Python
- PostgreSQL
- dbt Core
- Apache Airflow
- Streamlit
- scikit-learn
- Docker Compose
- Git

Kafka, Spark, Hadoop, Kubernetes, and unnecessary microservices are out of
scope. XGBoost may be evaluated later only if the baseline and simpler models
are already complete.

## 3. Guiding principles

1. Build a January 2024 vertical slice before scaling.
2. Every technology must have a clear course or project purpose.
3. Python owns source ingestion; dbt owns SQL transformations.
4. Airflow orchestrates independently testable operations and contains no large
   data-processing implementation.
5. Questionable records are classified and traceable, never silently discarded.
6. Monthly ingestion must be idempotent where practical.
7. Forecast features must not use information from the future.
8. Forecasting and recommendation logic are separate concerns.
9. Ownership does not create knowledge silos; all members review and understand
   the end-to-end system.
10. Readable and reproducible work is more valuable than unnecessary complexity.

## 4. Intended architecture

```text
NYC TLC monthly Parquet
        |
        v
Python download and source validation
        |
        v
PostgreSQL RAW + ingestion metadata
        |
        v
dbt staging + data-quality classification
        |
        v
Dimensional warehouse
        |
        +--------------------------+
        |                          |
        v                          v
Analytics marts          mart_zone_hour_demand
        |                          |
        v                          v
OLAP + analytics UI       Features + forecasting
                                   |
                                   v
                         Demand level + recommendation
                                   |
                                   v
                            Streamlit DSS page
```

Airflow will eventually orchestrate this flow. The underlying Python and dbt
steps must first work without Airflow so that they remain easy to test and debug.

## 5. Responsibility boundaries

### Python ingestion

- Download a requested source month
- Validate file format and expected source schema
- Calculate and record checksums
- Record batch and lineage metadata
- Enforce monthly idempotency and explicit replacement policy
- Load source records into PostgreSQL RAW

### dbt

- Canonical staging names and types
- Data-quality classification
- Dimensions and facts
- Analytical and DSS marts
- SQL-based data tests

### Airflow

- Orchestration only
- Parameter passing, task dependencies, retries, and status visibility
- Invocation of normal Python modules and dbt commands

### DSS

- Dense zone-hour demand dataset
- Leakage-safe feature engineering
- Baseline and model evaluation
- Day-ahead forecasts
- Demand levels and recommendations

### Dashboard

- Analytical and OLAP views
- Forecast context
- Interpretable DSS recommendations
- Database access through a service/repository layer rather than duplicated SQL
  inside every page

## 6. Balanced team ownership

The target contribution is approximately one third per member. Ownership means
accountability for delivery and documentation, not exclusive knowledge.

### Person 1 - Data engineering

Owns the path from the source file through stable staging data.

Primary responsibilities:

- Docker Compose and local infrastructure configuration
- PostgreSQL RAW and audit-layer requirements
- Python downloader and source manifest
- Parquet/schema validation and checksums
- Batch metadata and lineage
- Efficient RAW loading
- Monthly idempotency, incremental loading, and explicit backfill behavior
- dbt staging models
- Valid, quarantined, and rejected classification
- RAW-to-staging reconciliation
- Thin Airflow orchestration after the command-line pipeline is stable
- Ingestion, staging, and data-quality tests
- Pipeline operations and troubleshooting documentation

Person 1 delivers `stg_yellow_trip` and the agreed valid-data interface to
Person 2. Person 1 does not own dimensional warehouse or forecasting logic.

### Person 2 - Warehouse and analytics engineering

Owns the path from valid staging records through analytical marts and OLAP.

Primary responsibilities:

- Dimensional-model details and surrogate-key policy
- `dim_date`, `dim_time`, `dim_taxi_zone`, `dim_vendor`, and
  `dim_payment_type`
- `fact_trip`
- dbt relationships, uniqueness, accepted-value, and reconciliation tests
- `mart_zone_hour_demand`
- Only the additional KPI marts justified by dashboard queries
- OLAP roll-up, drill-down, slice, and dice queries
- Warehouse query performance and physical-design recommendations when measured
  performance requires them
- Overview and OLAP/analytics dashboard views
- Dimensional-model, data-dictionary, and OLAP documentation

Person 2 delivers `mart_zone_hour_demand` to Person 3. Person 2 does not own
source ingestion or forecasting-model evaluation.

### Person 3 - DSS and application

Owns the path from the demand mart through an interpretable recommendation.

Primary responsibilities:

- Business KPI definitions and exploratory analysis
- DSS feasibility analysis using samples or contract-compatible mock data early
  in the project
- Dense date-hour-zone grid and feature preparation
- Historical-demand baseline
- Leakage-safe time-based train, validation, and test split
- Simple model experiments after the baseline
- MAE, RMSE, and other justified evaluation metrics
- Demand-ratio and demand-level design
- Recommendation rules and explanation text
- DSS service/repository integration
- Demand Forecast and Recommendation dashboard view
- DSS limitations and evaluation documentation

Person 3 does not own the RAW pipeline or core dimensional models.

### Shared responsibilities

All three members participate in:

- Scope and data-contract reviews
- Pull-request review
- End-to-end integration and debugging
- Report writing for their respective components
- Final architecture and limitation review
- Slides, demo script, and presentation
- Understanding the business problem, dimensional model, ETL flow, and DSS
  design well enough to answer questions

## 7. Team handoff contracts

Detailed planned interfaces are documented in `docs/data_contracts.md`. The
following gates control when downstream work can integrate.

### Gate A - Person 1 to Person 2

Interface: `stg_yellow_trip` and its valid-record subset.

Required before integration:

- Canonical field names and types are documented
- Each row retains source lineage
- Each row has a data-quality state and reason where applicable
- Valid + quarantined + rejected counts reconcile to RAW for each batch
- Re-running an already successful source month does not duplicate records

Person 2 may develop against a fixture matching the contract before Gate A is
complete.

### Gate B - Person 2 to Person 3

Interface: `mart_zone_hour_demand`.

Required before integration:

- Grain is date x hour x pickup zone
- `trip_count` has one documented definition
- Date, hour, zone, borough, and zone name are available
- Zero-demand handling is documented
- Mart tests pass for grain and required fields
- No downstream Python code depends directly on RAW source column names

Person 3 may develop against contract-compatible sample or mock data before
Gate B is complete.

### Gate C - Person 3 to dashboard integration

Interface: forecast and recommendation result.

Required before integration:

- Forecast timestamp and target zone-hour are explicit
- Prediction is non-negative or has a documented post-processing rule
- Historical baseline and demand level are included
- Recommendation is separate from the numeric prediction
- Model and recommendation versions are identifiable

## 8. Dependency-ordered milestones

### Milestone 0 - Scope and contracts

Status: planning documents created; detailed interfaces remain TBD.

Deliverables:

- Frozen scope
- Responsibility boundaries
- Planned architecture
- Initial data contracts
- Agreed definition of the January vertical slice

Exit criteria:

- All members approve this plan
- Open design decisions required by Milestone 1 have named owners

### Milestone 1 - January 2024 vertical slice

Target flow:

```text
January Parquet
  -> RAW
  -> staging and data-quality status
  -> dimensions and fact_trip
  -> mart_zone_hour_demand
  -> one dashboard KPI or chart
```

Person 1:

- Ingest January into RAW with metadata
- Produce staging and data-quality classification
- Demonstrate an idempotent rerun

Person 2:

- Build the planned dimensions and `fact_trip`
- Build `mart_zone_hour_demand`
- Demonstrate one OLAP query

Person 3:

- Confirm KPI definitions through EDA
- Build one dashboard chart through the repository/service boundary
- Finalize the baseline and evaluation design without claiming a finished model

Exit criteria:

- One reproducible command sequence is documented
- RAW, staging, fact, mart, and dashboard counts reconcile
- No full-year download is required
- A rerun does not create duplicates
- Questionable records remain traceable

### Milestone 2 - Stable dimensional warehouse

Deliverables:

- Stable dimensions and fact grain
- dbt tests and documentation
- OLAP examples
- Minimal justified analytical marts

Exit criteria:

- Warehouse contracts are stable enough for multi-month ingestion
- Person 3 can use the DSS mart without reading the trip fact directly

### Milestone 3 - Incremental ingestion

Deliverables:

- January-March 2024 ingestion
- New-month detection
- Idempotent rerun behavior
- Explicit backfill or source-replacement policy
- Thin Airflow DAG wrapping the proven pipeline

Exit criteria:

- With January and February already loaded, running March adds only March
- Batch metadata explains every success, skip, and failure

### Milestone 4 - DSS baseline

Deliverables:

- Dense zone-hour series
- Historical baseline for each relevant zone-hour context
- Time-based evaluation split
- Baseline metrics
- Initial demand-level and recommendation contract

Exit criteria:

- No random time-series shuffle or future-data leakage
- A prediction is converted into an interpretable recommendation

### Milestone 5 - Model comparison and recommendation logic

Deliverables:

- At least one simple model compared with the baseline
- Documented feature availability at forecast time
- Evaluation by time period and relevant zone groups
- Justified demand-level thresholds
- Final recommendation logic

Exit criteria:

- The selected approach is justified by evidence, not model complexity
- The baseline may remain the final model if alternatives do not improve it

### Milestone 6 - Full-year 2024 load

Deliverables:

- Twelve monthly batches
- Reconciliation and data-quality summary by month
- Final time-based train, validation, and test periods

Exit criteria:

- Full-year loading does not require manual per-month code changes
- Data remains outside Git

### Milestone 7 - End-to-end integration

Deliverables:

- Overview view
- OLAP/analytics view
- Demand Forecast and Recommendation view
- Reproducible end-to-end demo path

Exit criteria:

- Dashboard queries marts or services, not copied SQL in every page
- Forecast, historical context, demand level, and recommendation agree
- All three members can explain the data flow

### Milestone 8 - Testing, documentation, and submission support

Deliverables:

- Final automated checks
- Setup and run instructions
- Architecture, dimensional model, ETL, OLAP, DSS, evaluation, and limitation
  documentation
- Small sample/reference data only
- Report and slide support

Exit criteria:

- A clean environment can follow the documented setup
- Required submission components are present
- Each member has a clear presentation section and evidence of contribution

## 9. Parallel development strategy

Work may proceed in parallel only against an agreed contract:

| Period | Person 1 | Person 2 | Person 3 |
|---|---|---|---|
| Before Gate A | Ingestion/RAW/staging | Warehouse models against fixture | EDA, KPI, DSS and UI contract |
| Gate A to Gate B | Incremental load and Airflow | Fact, dimensions, marts, OLAP | Baseline and UI against mart fixture |
| After Gate B | Reliability/backfill | Analytics UI and performance | Model, recommendation, DSS UI |
| Integration | Pipeline fixes | Warehouse/mart fixes | DSS/app fixes |

No member should wait for another member if a documented fixture can represent
the pending interface. Fixtures must be replaced by real interfaces at the
defined gate.

## 10. Git and review workflow

- Use a short-lived branch for each bounded task.
- Link work to an issue or agreed task description.
- Keep commits focused and descriptive.
- Require at least one other member to review non-trivial changes.
- Do not commit `.env`, full raw data, logs, dbt generated output, or model
  artifacts.
- Update this plan when scope, ownership, milestone order, or interface contracts
  materially change.
- Record why a design changed, not only what changed.

Suggested evidence of contribution:

- Issues and task ownership
- Pull requests and reviews
- Focused commits
- Documentation ownership
- Demonstrated component during the presentation

## 11. Intentionally unresolved decisions

These decisions are not implementation blockers until their owning milestone,
but they must be resolved and documented before dependent work begins:

- Final source and staging column types
- Data-quality thresholds for duration, distance, and monetary anomalies
- Unknown-zone handling
- Surrogate-key and slowly changing dimension policies
- Exact time-dimension resolution and NYC daylight-saving-time handling
- Monthly source-replacement procedure
- PostgreSQL physical partitioning and indexing
- Forecast feature set
- Train, validation, and test date boundaries
- Model-selection threshold relative to the baseline
- Demand-level thresholds
- Final dashboard layout and deployment method
- Final dependency versions and Docker topology

## 12. Definition of project success

The project is successful when the team can demonstrate:

1. Reproducible monthly ingestion with lineage and idempotency.
2. Explicit and auditable data-quality handling.
3. A documented dimensional warehouse with valid fact and dimension grains.
4. OLAP roll-up, drill-down, slice, and dice operations.
5. Marts that support dashboard and DSS use cases.
6. Leakage-safe day-ahead demand forecasting evaluated against a baseline.
7. An interpretable recommendation, not only a numeric prediction.
8. A concise dashboard showing both analytics and decision support.
9. Documentation and Git history that demonstrate balanced contributions from
   all three team members.
