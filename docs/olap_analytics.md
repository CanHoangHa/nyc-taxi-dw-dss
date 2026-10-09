# Warehouse OLAP and analytics view

## Metric and coverage

Every query below reads `mart.mart_zone_hour_demand`, whose row grain is an
**observed** New York local pickup date × hour × taxi zone. `trip_count` counts
valid Yellow Taxi trips whose pickup falls in that group. A row absent from the
mart means zero valid pickups **only inside a source month listed in
`mart.mart_demand_coverage`**. That view requires reconciled audit, fact, and
mart totals. Outside listed months it means unavailable data. The dashboard
stops a query if its selected period contains an unlisted month. It never estimates unmet
demand. Taxi zones 264 and 265 remain in all counts; they are real lookup
members. The synthetic unknown member is not present in this mart.

`src/dashboard/analytics_repository.py` provides the queries to the Streamlit
application. It takes a date interval, optional borough, inclusive hour range,
and optional set of taxi-zone IDs. Fixed allowlists supply grouping SQL; every
filter value is a PostgreSQL parameter. The UI shows at most 5,000 OLAP groups
at once and labels a truncated result, so a displayed subtotal is only called
a complete total when no rows were truncated.

## Runnable OLAP examples

Run these statements with `psql` against the project database. The January
examples use the first loaded source month; January-March are now available.
Change the literal date bounds for another period. All examples query the
mart, never RAW.

### Roll-up: daily zone-hour data to month and borough

```sql
SELECT date_trunc('month', demand_date)::date AS demand_month,
       borough,
       sum(trip_count)::bigint AS trip_count
FROM mart.mart_zone_hour_demand
WHERE demand_date >= DATE '2024-01-01'
  AND demand_date < DATE '2024-02-01'
GROUP BY 1, 2
ORDER BY 1, 2;
```

The sum across boroughs equals the `fact_trip` count for the selected pickup
period. A month is the calendar month of the **pickup timestamp**, not the
source-file month.

### Drill-down: month → day → day/hour for Manhattan

```sql
SELECT demand_date,
       demand_hour,
       sum(trip_count)::bigint AS trip_count
FROM mart.mart_zone_hour_demand
WHERE demand_date >= DATE '2024-01-01'
  AND demand_date < DATE '2024-02-01'
  AND borough = 'Manhattan'
GROUP BY demand_date, demand_hour
ORDER BY demand_date, demand_hour;
```

Omit `demand_hour` from `SELECT` and `GROUP BY` for the day level. Add
`pickup_location_id` and `zone_name` for the taxi-zone detail level. The UI
implements these levels as selectable groupings, so the same filters remain
active while the analyst drills down.

### Slice: one borough in one week, grouped by pickup hour

```sql
SELECT demand_hour,
       sum(trip_count)::bigint AS trip_count
FROM mart.mart_zone_hour_demand
WHERE demand_date BETWEEN DATE '2024-01-01' AND DATE '2024-01-07'
  AND borough = 'Manhattan'
GROUP BY demand_hour
ORDER BY demand_hour;
```

### Dice: two boroughs and the evening hours

```sql
SELECT borough,
       demand_hour,
       sum(trip_count)::bigint AS trip_count
FROM mart.mart_zone_hour_demand
WHERE demand_date BETWEEN DATE '2024-01-01' AND DATE '2024-01-31'
  AND borough IN ('Manhattan', 'Queens')
  AND demand_hour BETWEEN 17 AND 20
GROUP BY borough, demand_hour
ORDER BY borough, demand_hour;
```

The UI also permits dicing by an arbitrary selected set of TLC taxi-zone IDs.
Changing the date, borough, hour, or zone filter never changes the definition
of `trip_count`.

## Dashboard data dictionary

| Field | Type | Meaning |
|---|---|---|
| `demand_date` | `date` | New York local pickup date |
| `demand_hour` | `smallint` | New York local pickup hour, 0–23 |
| `pickup_zone_key` | `text` | Deterministic warehouse zone key |
| `pickup_location_id` | `integer` | TLC zone business ID |
| `borough` | `text` | Lookup borough label |
| `zone_name` | `text` | Lookup zone label |
| `trip_count` | `bigint` | Number of valid pickup trips in the row |

The Overview KPI `Chuyến đón hợp lệ` is `sum(trip_count)` under the active
filters; `Vùng có chuyến đón` is the number of distinct TLC pickup zone IDs
with a row under those filters; `Ngày có chuyến đón` is the number of distinct
pickup dates with a row. The daily, hourly, borough, and top-zone charts all
use the same pickup-trip measure and filters. The top-zone chart is ranked by
count, including zones 264/265 if they enter the top ten.

## Reconciliation and performance checks

For a selected fully built month, `sum(trip_count)` across mart rows must equal
the number of fact trips picked up in that calendar month. For the original
January load, this is 2,924,187; the dbt test
`assert_mart_zone_hour_reconciliation` checks **every** date-hour-zone, and
`assert_fact_trip_reconciliation` checks each source batch.

To inspect physical performance on the current local data, use:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT borough, sum(trip_count)::bigint AS trip_count
FROM mart.mart_zone_hour_demand
WHERE demand_date BETWEEN DATE '2024-01-01' AND DATE '2024-01-31'
GROUP BY borough;
```

The mart already has a unique B-tree index on
`(demand_date, demand_hour, pickup_zone_key)` to enforce its grain and help
bounded date queries. On the local January 2024 build (77,427 mart rows), the
borough roll-up above used a sequential scan and completed in **14.182 ms**
with 1,088 shared buffers hit (`EXPLAIN (ANALYZE, BUFFERS)`, 4 October 2026).
Scanning a small, month-wide table is appropriate for this query. A full-year
scan or a different index is a **measurement decision** after the remaining
months are loaded; adding indexes without a representative workload would slow
dbt rebuilds for an unproven benefit.

After the January-March build (240,554 mart rows), the same borough roll-up
over all three months completed in **19.823 ms** with 3,280 shared buffers hit
(`EXPLAIN (ANALYZE, BUFFERS)`, 8 October 2026). PostgreSQL chose a parallel
sequential scan. This single local measurement does not justify another index;
full-year performance remains to be measured after those months are loaded.
