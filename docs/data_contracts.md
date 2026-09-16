# Planned Data Contracts

## Status

- Contract version: `gate-a-v1-draft`
- Status: proposed for Person 2 review
- Implementation status: January 2024 source profile complete; ingestion not started

This document freezes the minimum interfaces required to let ingestion,
warehouse, and DSS work proceed independently. Physical table definitions,
materializations, and performance choices remain implementation decisions.

## Shared conventions

- Source dataset identifier: `yellow_taxi`
- Batch grain: one source year and month
- Source timestamps represent New York local wall-clock time
- Source timestamps are exposed as PostgreSQL `timestamp without time zone`
- The documented interpretation timezone is `America/New_York`
- Currency values are exposed to warehouse consumers as `numeric(12,2)`
- Source row identity is based on dataset, source month, and source row number;
  business-field equality is not used to remove trips
- Full raw data is never committed to Git

## Supporting contract: `audit.etl_batch`

- Producer: Python ingestion
- Consumers: pipeline operations, Airflow, reconciliation, and documentation
- Grain: one ingestion attempt for one source month

| Field | Planned type | Contract meaning |
|---|---|---|
| `batch_id` | `uuid` | Unique ingestion-attempt identifier |
| `dataset_name` | `text` | Fixed to `yellow_taxi` for this pipeline |
| `source_year` | `smallint` | Source partition year |
| `source_month` | `smallint` | Source partition month, 1-12 |
| `source_file` | `text` | Source filename |
| `source_file_sha256` | `char(64)` | Lowercase hexadecimal SHA-256 |
| `started_at` | `timestamptz` | Attempt start time |
| `finished_at` | `timestamptz` | Attempt end time, nullable while running |
| `source_row_count` | `bigint` | Rows reported by the source file |
| `loaded_row_count` | `bigint` | Rows committed to RAW |
| `valid_count` | `bigint` | Staging valid count, populated after dbt |
| `quarantined_count` | `bigint` | Staging quarantine count, populated after dbt |
| `rejected_count` | `bigint` | Staging rejected count, populated after dbt |
| `status` | `text` | `started`, `succeeded`, `failed`, or `skipped` |
| `error_message` | `text` | Failure context, otherwise null |

Final constraints and the mechanism used for dbt to update classification counts
are TBD.

## Ingestion output: `raw.yellow_trip`

- Producer: Python ingestion
- Consumer: dbt staging
- Grain: one source Parquet row

### Purpose

- Preserve source values with minimal transformation
- Add deterministic source lineage
- Support monthly reconciliation and safe reruns
- Provide a stable dbt source boundary

### Source payload

The ingestion contract expects the 2024 Yellow Taxi fields listed below. Source
names and source-compatible values are preserved in RAW; dbt owns canonical
naming and consumer-facing types.

```text
VendorID
tpep_pickup_datetime
tpep_dropoff_datetime
passenger_count
trip_distance
RatecodeID
store_and_fwd_flag
PULocationID
DOLocationID
payment_type
fare_amount
extra
mta_tax
tip_amount
tolls_amount
improvement_surcharge
total_amount
congestion_surcharge
Airport_fee
```

The January 2024 source profile confirmed all 19 expected fields, with no
missing or unexpected fields. The reproducible evidence is recorded in
`docs/profiles/yellow_tripdata_2024_01.md`.

Observed Parquet types are:

- `int32`: `VendorID`, `PULocationID`, and `DOLocationID`
- `int64`: `passenger_count`, `RatecodeID`, and `payment_type`
- `timestamp[us]`: pickup and drop-off timestamps
- `large_string`: `store_and_fwd_flag`
- `double`: distance and all monetary source fields

RAW DDL should preserve these source-compatible shapes. Missing required fields
fail source validation; unexpected additional fields are recorded and require
an explicit contract decision.

### Required lineage fields

| Field | Planned type | Contract meaning |
|---|---|---|
| `batch_id` | `uuid` | Ingestion attempt that produced the row |
| `source_dataset` | `text` | `yellow_taxi` |
| `source_year` | `smallint` | Source file year |
| `source_month` | `smallint` | Source file month |
| `source_file` | `text` | Source filename |
| `source_file_sha256` | `char(64)` | Source content checksum |
| `source_row_number` | `bigint` | Zero-based row position within the source file |
| `ingested_at` | `timestamptz` | RAW ingestion timestamp |

Planned source-row uniqueness:

```text
(source_dataset, source_year, source_month, source_row_number)
```

### Monthly idempotency policy

- A successful month with the same checksum is skipped on rerun.
- A successful month with a different checksum fails safely and requires an
  explicit `replace-month` operation.
- Replacement behavior will delete and reload the complete month in one
  controlled operation; its implementation is deferred to the incremental-load
  milestone.
- A failed attempt must not expose a partially committed RAW batch.

## Shared reference: Taxi Zone Lookup

- Source artifact: `data/reference/taxi_zone_lookup.csv`
- Producer: Person 1 makes the reviewed reference file available to dbt
- Consumers: Person 1 staging validation and Person 2 `dim_taxi_zone`
- Grain: one TLC `LocationID`

Minimum canonical fields:

| Field | Planned type | Contract meaning |
|---|---|---|
| `location_id` | `integer` | TLC taxi-zone business identifier |
| `borough` | `text` | Borough display name |
| `zone_name` | `text` | Taxi-zone display name |
| `service_zone` | `text` | TLC service-zone classification |

The dbt seed/source name and seed path remain TBD until dbt project setup.
Person 1 owns source availability and contract validation; Person 2 owns the
warehouse dimension built from it.

## Staging output: `stg_yellow_trip`

- Producer: dbt staging
- Consumers: data-quality reporting and `stg_yellow_trip_valid`
- Grain: one normalized RAW trip record

### Canonical interface

| Field | Planned type | Null policy / meaning |
|---|---|---|
| `trip_source_key` | `text` | Non-null deterministic source-row key |
| `batch_id` | `uuid` | Non-null lineage key |
| `source_year` | `smallint` | Non-null source partition year |
| `source_month` | `smallint` | Non-null source partition month |
| `source_file` | `text` | Non-null source filename |
| `source_row_number` | `bigint` | Non-null source row position |
| `vendor_id` | `smallint` | Nullable source vendor code |
| `pickup_datetime` | `timestamp` | Required for a valid record |
| `dropoff_datetime` | `timestamp` | Required for a valid record |
| `passenger_count` | `smallint` | Nullable source-reported value |
| `trip_distance` | `double precision` | Source distance in miles |
| `rate_code_id` | `smallint` | Nullable source rate-code value |
| `store_and_forward_flag` | `text` | Canonical `Y`, `N`, or null |
| `pickup_location_id` | `integer` | Must resolve to zone reference for validity |
| `dropoff_location_id` | `integer` | Must resolve to zone reference for validity |
| `payment_type_id` | `smallint` | Nullable source payment-type code |
| `fare_amount` | `numeric(12,2)` | Source fare amount |
| `extra_amount` | `numeric(12,2)` | Source extra amount |
| `mta_tax_amount` | `numeric(12,2)` | Source MTA tax amount |
| `tip_amount` | `numeric(12,2)` | Recorded tip amount |
| `tolls_amount` | `numeric(12,2)` | Source toll amount |
| `improvement_surcharge_amount` | `numeric(12,2)` | Source improvement surcharge |
| `total_amount` | `numeric(12,2)` | Total amount recorded by the source |
| `congestion_surcharge_amount` | `numeric(12,2)` | Source congestion surcharge |
| `airport_fee_amount` | `numeric(12,2)` | Source airport fee |
| `trip_duration_minutes` | `double precision` | Derived from drop-off minus pickup |
| `dq_status` | `text` | `valid`, `quarantined`, or `rejected` |
| `dq_reason_codes` | `text[]` | Empty for valid rows; one or more codes otherwise |

`trip_source_key` will be a deterministic digest of the dataset identifier,
source year, source month, and source row number. It will not be a hash of trip
business fields because two legitimate trips may share the same values.

### Initial classification policy

Rejected records are structurally unusable for trip analysis, including:

- Null pickup timestamp
- Null drop-off timestamp
- Drop-off timestamp earlier than pickup timestamp
- Required values that cannot be converted to the canonical type

Quarantined records are parseable but analytically questionable, including:

- Pickup or drop-off location missing from the Taxi Zone Lookup
- Negative trip distance
- Non-positive or unusually long duration
- Negative monetary values

Valid records satisfy all implemented rejection and quarantine rules.

Exact upper bounds for distance and duration remain TBD until January profiling.
Negative monetary records are quarantined rather than silently removed because
they may represent adjustments or disputes.

### Reconciliation invariant

For every successfully staged batch:

```text
raw row count
  = valid row count
  + quarantined row count
  + rejected row count
```

Every RAW row must appear exactly once in this classification.

## Warehouse handoff: `stg_yellow_trip_valid`

- Producer: Person 1 / dbt staging
- Consumer: Person 2 / dbt warehouse models
- Grain: one normalized trip record with `dq_status = 'valid'`

This is the Gate A interface. It exposes the canonical fields from
`stg_yellow_trip` and excludes `dq_status` values other than `valid`. Physical
materialization as a view or table is TBD.

Gate A is ready when:

- The canonical names and types above are implemented and documented.
- `trip_source_key` is non-null and unique.
- `batch_id` and source lineage are retained.
- Data-quality counts reconcile to RAW.
- An already successful source month can be rerun without duplication.
- Person 2 can build the warehouse without reading TLC source column names.

## Warehouse output: `fact_trip`

- Producer: Person 2 / dbt warehouse models
- Consumers: analytical marts and OLAP queries
- Grain: one valid Yellow Taxi trip

The fact is expected to consume `stg_yellow_trip_valid`, retain
`trip_source_key`, and reference pickup and drop-off date, time, and taxi-zone
roles plus vendor and payment-type dimensions. Exact surrogate keys and the
final measure set are owned by Person 2 and remain TBD.

Person 1 guarantees canonical timestamps, business identifiers, measures, and
lineage. Person 1 does not generate warehouse surrogate keys.

## DSS handoff: `mart_zone_hour_demand`

- Producer: Person 2 / dbt mart models
- Consumers: Person 3 / DSS feature preparation and dashboard
- Grain: date x hour x pickup zone

Minimum planned fields:

| Field | Contract meaning |
|---|---|
| `demand_date` | New York local calendar date |
| `demand_hour` | New York local hour, 0-23 |
| `pickup_zone_key` | Warehouse taxi-zone surrogate key |
| `pickup_location_id` | TLC business identifier |
| `borough` | Zone borough |
| `zone_name` | Zone display name |
| `trip_count` | Count of valid pickup trips in the grain |

Zero-demand representation, additional metrics, lag features, and physical
materialization remain TBD and are owned by Persons 2 and 3 at Gate B.
