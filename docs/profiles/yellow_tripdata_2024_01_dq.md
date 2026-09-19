# Yellow Taxi 2024-01 Staging Data Quality

## Run result

- RAW rows: 2,964,624
- Staging rows: 2,964,624
- Reconciliation: passed
- dbt tests: 22 passed, 0 failed
- Taxi Zone Lookup seed: 265 rows

## Classification

| Status | Rows | Share of RAW |
|---|---:|---:|
| valid | 2,924,187 | 98.6360% |
| quarantined | 40,381 | 1.3621% |
| rejected | 56 | 0.0019% |

The three statuses are mutually exclusive and sum to the RAW row count. The
`stg_yellow_trip_valid` view contains 2,924,187 rows.

## Reason codes

| Reason code | Rows |
|---|---:|
| `NEGATIVE_MONETARY_VALUE` | 37,578 |
| `EXCESSIVE_DURATION` | 1,983 |
| `NON_POSITIVE_DURATION` | 870 |
| `DROPOFF_BEFORE_PICKUP` | 56 |
| `PICKUP_OUTSIDE_SOURCE_MONTH` | 18 |

A row can have more than one reason code, so reason counts do not need to sum
to status counts. Rejected status takes priority over quarantined status.

The remaining implemented reason codes had zero rows for this month:
`MISSING_PICKUP_DATETIME`, `MISSING_DROPOFF_DATETIME`,
`UNKNOWN_PICKUP_ZONE`, `UNKNOWN_DROPOFF_ZONE`, and
`NEGATIVE_TRIP_DISTANCE`.

## Rules used

- Reject missing timestamps or drop-off before pickup.
- Quarantine unknown taxi zones, negative trip distance, pickup timestamps
  outside the source month, duration at or below zero, duration over 180
  minutes, or any negative monetary field.
- Classify all remaining rows as valid.
