# Warehouse data dictionary

This dictionary describes the Person 2 dbt output. Dates and times are New
York **local wall-clock values**; source timestamps have no UTC offset. The
complete row-level source and data-quality contract is in `data_contracts.md`.
Warehouse tables are rebuilt from valid staging/seed state by dbt, without
querying RAW directly.

## Dimensions in `dw`

| Table | Grain | Key and attributes |
|---|---|---|
| `dim_date` | One calendar date, plus unknown | `date_key` integer (`YYYYMMDD`, unknown `0`); `calendar_date` date; `iso_year`, `iso_week`, `iso_day_of_week`, `calendar_year`, `calendar_quarter`, `calendar_month`, `day_of_month` smallint; `is_weekend`, `is_unknown` boolean. ISO weekday is 1=Monday through 7=Sunday. |
| `dim_time` | One local minute of day, plus unknown | `time_key` smallint (`minute_of_day + 1`, unknown `0`); `time_of_day` time; `hour_of_day`, `minute_of_hour`, `minute_of_day` smallint; `is_unknown` boolean. There are 1,440 known minute members. |
| `dim_taxi_zone` | One TLC zone ID from the seed, plus unknown | `zone_key` text deterministic MD5 key; `location_id` integer TLC ID; `borough`, `zone_name`, `service_zone` text from the seed; `is_unknown` boolean. The same table serves pickup and drop-off roles. IDs 264 and 265 are real seed members, separate from unknown. |
| `dim_vendor` | One observed non-null vendor ID, plus unknown | `vendor_key` text deterministic MD5 key; `vendor_id` smallint; `vendor_name` text; `is_unknown` boolean. New source codes receive an explicit unmapped label. |
| `dim_payment_type` | One observed non-null payment code, plus unknown | `payment_type_key` text deterministic MD5 key; `payment_type_id` smallint; `payment_type_name` text; `is_unknown` boolean. Payment code `0` is a real code, not unknown. |

Known taxi-zone, vendor, and payment keys are stable MD5 digests of the
dimension name and business ID. Their unknown key is 32 zero characters.
Unknown members have null business ID/date/time attributes and
`is_unknown=true`. Detailed key formulas and join rules are in
`dimensional_model.md`.

## `dw.fact_trip`

Grain: **one valid Yellow Taxi source row**. `trip_source_key` is unique and
stable for its dataset/source month/zero-based source-row number. Two trips
with identical business values remain two fact rows. No questionable or
rejected staging row enters the fact.

| Columns | PostgreSQL type | Meaning |
|---|---|---|
| `trip_source_key` | text | Stable fact identifier and source-row identity. |
| `batch_id` | uuid | Ingestion attempt that produced the source row. |
| `source_dataset`, `source_file` | text | Dataset and source filename for lineage. |
| `source_year`, `source_month` | smallint | Source file partition, not necessarily the drop-off calendar period. |
| `source_file_sha256` | char(64) | Source artifact checksum. |
| `source_row_number` | bigint | Zero-based position in the Parquet file. |
| `ingested_at` | timestamptz | RAW ingestion instant. |
| `pickup_date_key`, `dropoff_date_key` | integer | Role-specific references to `dim_date.date_key`. |
| `pickup_time_key`, `dropoff_time_key` | smallint | Role-specific references to `dim_time.time_key`, using the local minute containing the timestamp. |
| `pickup_zone_key`, `dropoff_zone_key` | text | Role-specific references to `dim_taxi_zone.zone_key`. |
| `vendor_key`, `payment_type_key` | text | Dimension references; null source codes map to the unknown member. |
| `pickup_datetime`, `dropoff_datetime` | timestamp without time zone | Exact source local timestamps; seconds/subseconds are retained. |
| `pickup_location_id`, `dropoff_location_id` | integer | Original TLC zone business IDs for tracing. |
| `vendor_id`, `payment_type_id`, `rate_code_id` | smallint | Original canonical business codes; vendor/payment may be null. |
| `store_and_forward_flag` | text | Canonical source flag (`Y`, `N`, or null). |
| `trip_count` | integer | Constant `1` per valid trip; additive trip-count measure. |
| `passenger_count` | smallint | Source-reported passenger count; nullable. |
| `trip_distance` | double precision | Source trip distance in miles; nullable. |
| `trip_duration_minutes` | double precision | Drop-off minus pickup in minutes. |
| `fare_amount`, `extra_amount`, `mta_tax_amount`, `tip_amount`, `tolls_amount`, `improvement_surcharge_amount`, `total_amount`, `congestion_surcharge_amount`, `airport_fee_amount` | numeric(12,2) | Source-reported currency components; nullable values remain null. `total_amount` is not recomputed. |

The date/time/zone foreign keys are required and are tested for non-null and
dimension coverage. `trip_source_key` has a unique index. The fact retains
exact timestamps and canonical source measures, so dimension groupings never
replace traceable original values. Staging-to-fact reconciliation checks row
count, summed `trip_count`, and `total_amount` by batch.

## `mart.mart_zone_hour_demand`

Grain: one **observed** local pickup date × hour × pickup zone. There is no row
for a combination without a valid pickup. The column-level dictionary,
zero-demand/coverage rule, and reconciliation counts are in `gate_b_handoff.md`.
The mart has a unique index on `(demand_date, demand_hour, pickup_zone_key)`.
Its `trip_count` is `bigint`, because it sums `fact_trip.trip_count`. It carries
the zone's TLC ID, borough, and name for DSS and analytics consumers.
`is_recommendation_eligible` is true for TLC LocationIDs 1–263 and false for
264 (`N/A`), 265 (`Outside of NYC`), and the synthetic unknown member. The
special zones remain in mart totals for reconciliation.

## `mart.mart_demand_coverage`

A view with one row per fully reconciled source/pickup month. It exposes
`source_year` and `source_month` (`smallint`), inclusive
`coverage_start_date` and `coverage_end_date` (`date`), and
`valid_trip_count` (`bigint`). A listed month permits filling missing sparse
mart cells with zero; an unlisted month does not. See `gate_b_handoff.md`.
