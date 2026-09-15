# Planned Dimensional Model

No warehouse tables have been implemented yet.

## Fact

### `fact_trip`

Grain: one valid NYC Yellow Taxi trip.

The fact will reference pickup and drop-off date/time members, pickup and
drop-off taxi zones, vendor, and payment type. Its final key and measure set is
TBD.

## Dimensions

| Dimension | Planned grain |
|---|---|
| `dim_date` | One calendar date |
| `dim_time` | One time-of-day member; final resolution TBD |
| `dim_taxi_zone` | One NYC TLC taxi-zone member |
| `dim_vendor` | One source vendor code |
| `dim_payment_type` | One payment-type code |

`dim_taxi_zone` is a role-playing dimension referenced by both pickup and
drop-off foreign keys. Separate physical pickup and drop-off dimensions are not
planned.

Surrogate-key strategy, unknown-member policy, slowly changing dimension policy,
and physical indexing or partitioning remain TBD.
