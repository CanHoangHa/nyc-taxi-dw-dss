# Warehouse OLAP and analytics view

## Interactive dashboard (30 October 2026)

All dashboard labels, axes, tooltips and presentation text are in English.
Time and geography back buttons sit beside their respective chart headings.
Forecast ranking shows rank, zone and forecast/D−7 totals; repeated rule text
and the same hour count on every row are omitted. Predictions display one decimal.
Hourly details, priority rules, model metadata and historical evaluation are
available in collapsed sections. Model/run identifiers remain available for
audit but no longer appear as a block of technical text above the main chart.
Persisted forecasts, recommendations and explanations are unchanged in the DB.
No pie chart was added: bar charts preserve direct comparisons between zones.

The **Average pickups by weekday and hour** heatmap follows the current OLAP exploration
scope, including applied dates, borough/zones, hours and subsequent drill-down.
It queries at most 168 weekday/hour totals and divides each by the number of
calendar occurrences of that weekday, including zero-pickup dates. Weekdays
outside the date interval have no denominator and are grey, not zero. Hover
shows the average and the number of **Matching dates**. For example, 500 pickups
at 18:00 across five Fridays means an average of 100 in the Friday/18 cell.
An average describes a historical pattern; it does not show variability or
guarantee the same count next Friday. No warehouse rebuild is required.

Forecast starts with a submitted **Planning scope** form and **Zones to review**.
Choose date, borough, half-open shift interval, optional zones and a shortlist
length (5/10/20), then press **Apply**. Invalid scope edits retain the previous
selection. Zones are ordered by forecast pickup volume; fleet availability
still has to be considered by the person planning service.

The supporting **Top zones: forecast vs. last week** chart uses both series
on the same prediction-selected shortlist. The collapsed **Hourly pattern by zone** heatmap
uses these same zones and hours, ordered by total prediction. Scope KPIs still
describe all filtered zones; shortlist size limits the table and zone charts.
Its values are
hourly forecasts, not historical averages. A one-hour selection uses only the
comparison chart. These views do not change ranking rules, model selection or
the fixed historical ranking evaluation policy.

Overview and OLAP use a submitted filter form. Edit dates, pickup borough,
inclusive pickup hours (6–9 includes 6, 7, 8, 9), and optional taxi zones, then
press **Apply filters**. Until submission, charts retain the applied selection;
a caption displays that selection. Empty zone selection means all zones inside
the chosen borough. Zone options include all boroughs so all fields can be
submitted together; an incompatible borough/zone choice is rejected rather
than silently producing zero. Invalid dates retain the previous applied scope.
Forecast/DSS has its own submitted planning form, separate from historical filters.

OLAP opens with monthly and borough bar charts. Click a bar (or use the labelled
select-and-drill controls) to drill month → day → hour or borough → taxi zone.
Both charts share the drilled scope; back buttons roll up one hierarchy at a
time, and **Reset exploration** resets both to the submitted filters. New applied
filters reset drill navigation. Time buckets with no valid pickups are shown
as zero only within reconciled coverage. Geography charts show the top 20
zones when necessary; the dropdown retains all zones with pickups. The total
above the charts always covers the entire scope, not only the displayed top 20.
The optional detail-table switch queries the combined time/geography grain and
offers CSV export, with the existing 5,000-group truncation warning.

Horizontal charts always show every category label, with 30 pixels per row.
Exact pickup totals appear beside the bars, so low-volume boroughs remain
readable on the shared zero-based linear scale even when Manhattan dominates.
Overview offers a 10 / 20 / 30 zone selector; this only changes the descriptive
chart length and does not modify the DSS evaluation's fixed K.

Overview KPIs are valid pickup count, average pickups per **calendar day** in
the selected interval (including zero-pickup days), and busiest pickup hour
aggregated across those days. Tied busiest hours use the earliest hour. These
replace the previous active-zone/active-day counts, which added little context
when selecting a single zone.

Reference loading now checks coverage once instead of twice and reuses the
same database connection for reference queries. Coverage still performs the
original audit/fact/mart reconciliation; no checks were weakened. Data caches
last five minutes. **Reload data** explicitly clears caches after a pipeline
update; it is separate from filter submission. The local `.env.example` uses
`127.0.0.1`: on this Windows machine, `localhost` incurred about five seconds
per connection versus about 0.02 seconds over IPv4. Restart an already-running
Streamlit process after changing `.env` because loaded environment variables
take precedence. Docker services continue to connect to `postgres` internally.

Local measured overview fetch: approximately 0.74 seconds uncached and 0.001
seconds cached. Initial reference/coverage load was about 13 seconds; this
remains dependent on database load and is not a performance guarantee.

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
examples use the first loaded source month; January-April are now available.
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

The Overview KPI `Valid pickups` is `sum(trip_count)` under the applied
filters. `Average pickups / day` divides that sum by the inclusive calendar
day count. `Busiest pickup hour` is the hour with the largest aggregated pickup
count in that same scope. The daily, hourly, borough, and top-zone charts all
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
