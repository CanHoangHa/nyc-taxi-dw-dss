# Dimensional Model

The five dimensions and `fact_trip` are implemented as dbt tables in the `dw`
schema. `mart_zone_hour_demand` is implemented in `mart`. Warehouse models consume only
`stg_yellow_trip_valid` and the `taxi_zone_lookup` seed.

The demand mart reads only `fact_trip` and its dimensions. It has one row per
observed pickup date × hour × taxi zone, with a positive `trip_count` equal to
the number of valid trips. The mart is sparse: it does not materialize zero-trip
combinations. Zero-demand and source-coverage interpretation are specified in
`docs/gate_b_handoff.md`.

## Fact

### `fact_trip`

Grain: one valid NYC Yellow Taxi trip.

The fact consumes `stg_yellow_trip_valid`. It references pickup and
drop-off date/time members, pickup and drop-off taxi zones, vendor, and payment
type.

The Person 1 handoff guarantees these source-level groups:

- Stable `trip_source_key` and batch lineage
- Exact pickup and drop-off timestamps
- Pickup and drop-off TLC Location IDs
- Vendor and payment-type business identifiers
- Passenger, distance, duration, fare, tip, toll, surcharge, fee, and total
  amount values

Its primary identifier is the source's stable `trip_source_key`, with a unique
index. All joins to dimensions are left joins so a missing mapping cannot
silently discard a trip; non-null/relationship tests then fail on an unresolved
key. Null vendor and payment codes map to the dedicated unknown members.

The fact retains every available canonical measure: `trip_count = 1`,
`passenger_count`, `trip_distance`, `trip_duration_minutes`, `fare_amount`,
`extra_amount`, `mta_tax_amount`, `tip_amount`, `tolls_amount`,
`improvement_surcharge_amount`, `total_amount`,
`congestion_surcharge_amount`, and `airport_fee_amount`. It also keeps
`rate_code_id`, `store_and_forward_flag`, source business IDs, exact timestamps,
and batch/source lineage. Nullable measures stay null; they are not replaced
with zero. Amounts remain `numeric(12,2)` and duration remains double precision
as provided by staging. The date and minute roles are for grouping; the exact
timestamps remain available for auditing.

## Dimensions

| Dimension | Planned grain |
|---|---|
| `dim_date` | One calendar date |
| `dim_time` | One New York local minute of day (approved by Person 2) |
| `dim_taxi_zone` | One NYC TLC taxi-zone member |
| `dim_vendor` | One source vendor code |
| `dim_payment_type` | One payment-type code |

`dim_taxi_zone` is a role-playing dimension referenced by both pickup and
drop-off foreign keys. Separate physical pickup and drop-off dimensions are not
planned.

## Key and unknown-member policy

| Dimension | Key | Known member | Unknown member |
|---|---|---|---|
| `dim_date` | `date_key` integer | `YYYYMMDD` for `calendar_date` | `0`, null date |
| `dim_time` | `time_key` smallint | `minute_of_day + 1`, from 1 to 1440 | `0`, null time |
| `dim_taxi_zone` | `zone_key` text | MD5 of `dim_taxi_zone\|` + `location_id` | 32 zero characters, null `location_id` |
| `dim_vendor` | `vendor_key` text | MD5 of `dim_vendor\|` + `vendor_id` | 32 zero characters, null `vendor_id` |
| `dim_payment_type` | `payment_type_key` text | MD5 of `dim_payment_type\|` + `payment_type_id` | 32 zero characters, null `payment_type_id` |

The deterministic keys survive table rebuilds and do not shift when new codes
appear. Every dimension has exactly one `is_unknown = true` row. Null source
vendor/payment IDs map to that row; TLC payment code `0` is **Flex Fare**, not
the unknown row. Taxi-zone codes 264 (`N/A`) and 265 (`Outside of NYC`) are
real seed members with distinct keys; neither is the fallback row.
`is_recommendation_eligible` is true only for TLC zone IDs 1–263. Zones 264
and 265 stay in the fact and demand mart for total reconciliation, while they
and the synthetic unknown member are excluded from dispatch recommendations.

`dim_date` spans every calendar date between the earliest pickup/dropoff and
latest pickup/dropoff among valid staging rows. This includes a dropoff across
the January/February boundary. `dim_time` contains all 1,440 local clock
minutes, with no date or UTC offset. Its fields include `hour_of_day` (0–23)
and `minute_of_hour` (0–59). Source timestamps have no timezone offset, so a
repeated daylight-saving minute cannot be distinguished from another occurrence
using the current input. The fact keeps the exact source timestamps
alongside date/time keys.

`dim_vendor` and `dim_payment_type` contain observed non-null codes from valid
staging, plus the unknown row. Labels for recognized codes follow the
[TLC Yellow Taxi data dictionary](https://www.nyc.gov/assets/tlc/downloads/pdf/data_dictionary_trip_records_yellow.pdf)
(published in 2025); an unrecognized future code keeps its own member with an
explicit `Unmapped ... code` label. The dimensions are rebuilt from current
staging/seed data on each dbt run. This is a Type 1 snapshot: label updates
replace old labels. Physical indexes and partitioning will be chosen after
fact/mart query patterns are measured.

## Mapping in `fact_trip`

- For each timestamp, cast to `date` to join `dim_date.calendar_date`.
- Convert the local hour and minute to `hour * 60 + minute + 1` to join
  `dim_time.time_key`. Seconds remain in the original timestamp; no rounding.
- Join both pickup and dropoff `location_id` values to the same
  `dim_taxi_zone.location_id` and assign role-specific foreign keys.
- Join `vendor_id` and `payment_type_id` to the matching business-code columns;
  use the unknown member when the source code is null. A novel non-null code
  first creates its own dimension member on rebuild.
- The fact retains `trip_source_key`, batch/source lineage, and exact timestamps
  to support reconciliation and debugging.

## Role boundary

Person 1 produces canonical valid staging rows but does not create warehouse
surrogate keys. Person 2 must not depend directly on TLC source column names or
the RAW table. This boundary allows ingestion and warehouse work to evolve
independently after Gate A is approved.
