# Gate B handoff — January-March 2024 demand mart

Status: producer implementation complete on `feature/warehouse-foundation`;
Person 3 consumer review is pending. The branch incorporates the latest
`develop` ingestion and Airflow work, including January-March RAW/staging.

## Interface

`mart.mart_zone_hour_demand` is a dbt table built from `dw.fact_trip` and the
date, time, and taxi-zone dimensions. Its grain is one **New York local pickup
date × hour × pickup taxi zone** with at least one valid pickup. No RAW columns
or RAW table are used by the mart.

| Column | Type | Meaning |
|---|---|---|
| `demand_date` | `date` | Local date of pickup |
| `demand_hour` | `smallint` | Local hour of pickup, 0–23 |
| `pickup_zone_key` | `text` | Key of `dw.dim_taxi_zone` |
| `pickup_location_id` | `integer` | TLC zone business identifier |
| `borough` | `text` | Zone borough from the versioned seed |
| `zone_name` | `text` | Zone display name from the versioned seed |
| `trip_count` | `bigint` | Count of valid pickup trips in this grain |

The mart retains zones 264 (`N/A`) and 265 (`Outside of NYC`) when valid trips
use them. They contribute to reconciliation, but Person 3 should decide whether
they are actionable recommendation targets before modeling. The synthetic
unknown dimension member has no valid pickup trips in the current dataset.

## Zero-demand and coverage policy

The mart is **sparse**: it emits only observed combinations, all with
`trip_count > 0`. Within a source month successfully ingested and rebuilt
through this mart, an absent date-hour-zone combination means **zero valid
pickups in this dataset**. Outside loaded months, absence means **unavailable
data**, not zero demand. January-March 2024 are currently loaded. Person 3 owns
the dense date-hour-zone grid used for forecasting and must apply this coverage
boundary before filling absent combinations with zero. The grid should use
real taxi-zone seed members, excluding the synthetic unknown member.

## January-March reconciliation

| Pickup/source month | Valid staging = fact rows | Mart rows | Sum of mart `trip_count` | Observed pickup zones |
|---|---:|---:|---:|---:|
| 2024-01 | 2,924,187 | 77,427 | 2,924,187 | 260 |
| 2024-02 | 2,964,028 | 74,278 | 2,964,028 | 254 |
| 2024-03 | 3,520,696 | 88,849 | 3,520,696 | 259 |
| **Total** | **9,408,911** | **240,554** | **9,408,911** | — |

The observed date range is 2024-01-01 through 2024-03-31. The January
subset is unchanged from the original Gate B evidence; it includes 11,678
trips picked up in zone 264 or 265.

Validation on 30 September 2026: `dbt seed` passed; all nine selected staging,
warehouse, and mart models built; **88/88 dbt tests passed** (87 data tests and
one Gate A unit test). A second mart build produced the same 77,427 rows, same
trip total, and the same content fingerprint.

On 4 October 2026, all nine models were rebuilt again with the same fact and
mart row counts, and the full 88-test dbt suite passed. The Person 2 Overview
and OLAP application also reads this mart; its definitions and SQL examples
are in `docs/olap_analytics.md`. Person 3 consumer signoff is still pending.
After an explicit `numeric(12,2)` cast was added to fact monetary columns,
`fact_trip` and the mart were rebuilt with the same counts; all 38 selected
fact/mart tests, including the new physical-type test, passed.

On 8 October 2026, the merged three-month staging build contained 9,554,778
RAW rows and passed all 24 selected staging tests. The five dimensions,
`fact_trip`, and this mart were then rebuilt from all 9,408,911 valid Q1 trips.
The full dbt test suite passed **89/89** tests (88 data tests and one staging
unit test). The Airflow DAG currently stops after staging tests and audit-count
write-back; run the warehouse/mart dbt command separately after a new source
month arrives.

The mart model has a unique index on (`demand_date`, `demand_hour`,
`pickup_zone_key`). dbt tests check required fields, hour range, positive counts,
grain uniqueness, dimension relationships, and exact counts for every
date-hour-zone against independently grouped `fact_trip` timestamps.

## Reproduce

From the repository root with PostgreSQL running and `.env` configured:

```powershell
.\.venv\Scripts\dotenv.exe -f .env run -- .\.venv\Scripts\dbt.exe seed --project-dir src/dbt --profiles-dir src/dbt
.\.venv\Scripts\dotenv.exe -f .env run -- .\.venv\Scripts\dbt.exe run --project-dir src/dbt --profiles-dir src/dbt --select staging warehouse marts
.\.venv\Scripts\dotenv.exe -f .env run -- .\.venv\Scripts\dbt.exe test --project-dir src/dbt --profiles-dir src/dbt
```

Consumer signoff should confirm the sparse zero-demand contract and treatment
of zone IDs 264/265 before Gate B is marked accepted.
