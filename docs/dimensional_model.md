# Planned Dimensional Model

No warehouse tables have been implemented yet.

## Fact

### `fact_trip`

Grain: one valid NYC Yellow Taxi trip.

The fact will consume `stg_yellow_trip_valid`. It will reference pickup and
drop-off date/time members, pickup and drop-off taxi zones, vendor, and payment
type.

The Person 1 handoff guarantees these source-level groups:

- Stable `trip_source_key` and batch lineage
- Exact pickup and drop-off timestamps
- Pickup and drop-off TLC Location IDs
- Vendor and payment-type business identifiers
- Passenger, distance, duration, fare, tip, toll, surcharge, fee, and total
  amount values

Person 2 owns warehouse surrogate keys, foreign-key resolution, and the final
fact measure selection. Exact timestamps should remain available for audit even
when date and time dimension keys are added.

## Dimensions

| Dimension | Planned grain |
|---|---|
| `dim_date` | One calendar date |
| `dim_time` | One local time-of-day member; final resolution requires Person 2 approval |
| `dim_taxi_zone` | One NYC TLC taxi-zone member |
| `dim_vendor` | One source vendor code |
| `dim_payment_type` | One payment-type code |

`dim_taxi_zone` is a role-playing dimension referenced by both pickup and
drop-off foreign keys. Separate physical pickup and drop-off dimensions are not
planned.

Surrogate-key strategy, unknown-member policy, slowly changing dimension policy,
and physical indexing or partitioning remain TBD.

## Role boundary

Person 1 produces canonical valid staging rows but does not create warehouse
surrogate keys. Person 2 must not depend directly on TLC source column names or
the RAW table. This boundary allows ingestion and warehouse work to evolve
independently after Gate A is approved.
