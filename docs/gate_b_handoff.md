# Gate B handoff — January-March 2024 demand mart

Status: **accepted by Person 3 on 9 October 2026** after contract review and
consumer-side validation. The branch incorporates the latest
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
| `is_recommendation_eligible` | `boolean` | True only for dispatchable TLC zones 1–263 |
| `trip_count` | `bigint` | Count of valid pickup trips in this grain |

The mart retains zones 264 (`N/A`) and 265 (`Outside of NYC`) when valid trips
use them. They contribute to reconciliation and analytical totals, but have
`is_recommendation_eligible = false` and must not enter the dispatch grid or
recommendations. Only zones 1–263 are recommendation targets. The synthetic
unknown dimension member also has `is_recommendation_eligible = false` and must
be excluded entirely from the recommendation grid.

## Zero-demand and coverage policy

The mart is **sparse**: it emits only observed combinations, all with
`trip_count > 0`. The separate `mart.mart_demand_coverage` dbt **view** publishes
one row per month that has reconciled staging audit counts, `dw.fact_trip`, and
the demand mart. Its interface is:

| Column | Type | Meaning |
|---|---|---|
| `source_year` | `smallint` | Source/pickup year |
| `source_month` | `smallint` | Source/pickup month, 1–12 |
| `coverage_start_date` | `date` | First calendar day of the month, inclusive |
| `coverage_end_date` | `date` | Last calendar day of the month, inclusive |
| `valid_trip_count` | `bigint` | Classified valid trips; equals fact and mart totals |

A month appears only when every successful ingestion batch for that month has
classified counts and the monthly valid total equals both fact and mart totals.
The view checks this when queried, so a newly loaded month cannot be treated
as covered before rebuilding the fact and mart. Existing dbt reconciliation
tests additionally compare every observed mart cell against independently
grouped fact trips. A row in this view is the positive evidence for zero-fill;
`min(demand_date)` and `max(demand_date)` alone are insufficient. An absent
date-hour-zone combination **inside a listed month** means zero valid pickups.
An absent combination in an unlisted month means data unavailable, including
gaps between two listed months. Person 3 owns the dense hourly grid and must
join it to the listed coverage months before zero-filling. Build that grid from
`dw.dim_taxi_zone WHERE is_recommendation_eligible`, not all dimension members.

The view assumes the Gate A rule that valid pickup timestamps fall inside
their source month; keep the full dbt tests green when refreshing data. It
establishes monthly batch completeness, not the arrival status of future TLC
files that have never been ingested.

Example historical training grid for Person 3 (one row per covered
date × hour × recommendation-eligible zone):

```sql
select
    d.calendar_date as demand_date,
    h.demand_hour,
    z.zone_key as pickup_zone_key,
    z.location_id as pickup_location_id,
    coalesce(m.trip_count, 0) as trip_count
from dw.dim_date as d
join mart.mart_demand_coverage as c
    on d.calendar_date between c.coverage_start_date and c.coverage_end_date
cross join generate_series(0, 23) as h(demand_hour)
cross join dw.dim_taxi_zone as z
left join mart.mart_zone_hour_demand as m
    on m.demand_date = d.calendar_date
    and m.demand_hour = h.demand_hour
    and m.pickup_zone_key = z.zone_key
where z.is_recommendation_eligible;
```

## Day-ahead publication contract for Person 3

For day D, publish the entire 24-hour forecast only after observed data through
23:59 on D−1 are available. A feature for any hour of D may use `lag_24`,
`lag_48`, `lag_168`, calendar features known in advance, and rolling statistics
shifted by at least 24 hours. `lag_1` for hours 01–23 would require actual
observations from day D and leak future information under this publication
contract. Person 3 owns feature preparation, forecasting, and recommendation
logic; this document defines the shared input and timing boundary.

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

On 9 October 2026, the recommendation flag and monthly coverage view were
built against the same Q1 data. Coverage returned three distinct months with
`valid_trip_count` 2,924,187, 2,964,028, and 3,520,696, exactly matching the
fact and mart monthly totals above. Zone 263 was eligible; zones 264, 265,
and the unknown member were ineligible. The mart remained at 240,554 positive
rows. The full dbt suite passed **99/99** tests, the analytics repository
integration suite passed **3/3**, and the Streamlit AppTest reported no
exceptions or warnings.

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

Person 3 acceptance confirms the coverage interface, sparse zero-demand
contract, zone eligibility, and day-ahead publication boundary. The consumer
implementation reads only the published coverage view, eligible zone
dimension members, and demand mart. Its unit suite verifies covered zero-fill,
reconciliation, gap rejection, stable grain, and exclusion of ineligible zones.

This acceptance does not replace the producer evidence above and does not
claim final model quality: January-March is sufficient for a Q1 prototype,
while final evaluation still requires the planned full-year rebuild.
