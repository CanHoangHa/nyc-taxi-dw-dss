# January-March 2024 Ingestion Prototype

- Evidence collected: 2026-10-07
- Pipeline commit: `5d38229` (`feat: add ordered monthly backfill`)
- Branch: `feature/ingestion-pipeline`

This prototype verifies monthly RAW ingestion before adding Airflow. It does
not mark the complete incremental-ingestion milestone or Gate A review as
finished.

## Source and RAW evidence

All three official TLC Parquet files passed the existing exact-schema
validator. Source row counts, successful audit loaded counts, and physical
RAW counts agree for each month.

| Month | Source / RAW rows | Successful batch ID | Source row-number range |
|---|---:|---|---|
| 2024-01 | 2,964,624 | `ee53c473-cae2-444e-a842-329d1d020483` | 0-2,964,623 |
| 2024-02 | 3,007,526 | `6c780f5d-3d69-4efc-8acd-bcb517295063` | 0-3,007,525 |
| 2024-03 | 3,582,628 | `cd98d2d0-cc0d-4f2b-bf40-d3ddde6c05e4` | 0-3,582,627 |
| Total | 9,554,778 | Three source batches | |

Recorded SHA-256 checksums:

```text
2024-01 c4d59da7bbc8abaeeeb1727947ee93d9891a71acb42854bd80db1571b2030510
2024-02 c76c43c18c6c6664080dd920baab4928988d5786a6b65980792ca7cd796f9f20
2024-03 2d4cdc8fb96726cdd3803b13b02d2e61e71d45720aff0ebc693a8bdd1f249823
```

## Incremental and rerun evidence

| Step | January | February | March | Total RAW rows |
|---|---|---|---|---:|
| Backfill January-February | skipped | succeeded | absent | 5,972,150 |
| Backfill January-March | skipped | skipped | succeeded | 9,554,778 |
| Rerun January-March | skipped | skipped | skipped | 9,554,778 |

The March load added exactly 3,582,628 rows. January and February retained
their original successful batch IDs, row counts, and source row-number ranges.
The final rerun wrote three skipped audit attempts with `loaded_row_count = 0`:

| Month | Rerun batch ID |
|---|---|
| 2024-01 | `f2a026a7-9b3f-4e06-aada-1b43d5ae3475` |
| 2024-02 | `436390a5-e241-4dfa-b009-edfd97f1efce` |
| 2024-03 | `34c9809f-c880-4bf1-a4ac-244582a5000f` |

Each month commits independently. Backfill stops on its first failed month;
retrying the same range skips earlier successes and retries the failed month.
Changed-checksum replacement still fails without modifying existing RAW.

## Staging classification

The full staging rebuild produced 9,554,778 rows. Each month's classified
count equals its RAW count; January retained its previous DQ counts.

| Month | RAW / staging rows | Valid | Quarantined | Rejected |
|---|---:|---:|---:|---:|
| 2024-01 | 2,964,624 | 2,924,187 | 40,381 | 56 |
| 2024-02 | 3,007,526 | 2,964,028 | 43,491 | 7 |
| 2024-03 | 3,582,628 | 3,520,696 | 61,815 | 117 |
| Total | 9,554,778 | 9,408,911 | 145,687 | 180 |

Reason counts:

| Reason code | January | February | March |
|---|---:|---:|---:|
| `DROPOFF_BEFORE_PICKUP` | 56 | 7 | 117 |
| `EXCESSIVE_DURATION` | 1,983 | 1,948 | 2,172 |
| `NEGATIVE_MONETARY_VALUE` | 37,578 | 40,741 | 58,625 |
| `NON_POSITIVE_DURATION` | 870 | 803 | 1,128 |
| `PICKUP_OUTSIDE_SOURCE_MONTH` | 18 | 15 | 23 |

All other implemented reason codes, including `CANONICAL_TYPE_OUT_OF_RANGE`
and `NON_FINITE_NUMERIC_VALUE`, have zero rows in these source files. A row
can have multiple reasons; reason counts are not mutually exclusive.

The existing DQ policy was applied to all three months, including the
180-minute duration rule. This run verifies that the pipeline processes the
additional months; it does not independently validate or revise the business
thresholds.

## Verification result

- Python unit and PostgreSQL integration tests: 48 passed, 0 failed.
- dbt seed: 265 Taxi Zone Lookup rows.
- dbt staging models: 2 passed, 0 failed.
- dbt tests against the three-month dataset: 24 passed, 0 failed
  (23 data tests and 1 numeric-edge-case unit test).
- Per-batch RAW-to-staging reconciliation, DQ reason consistency,
  source-row/key uniqueness, and Gate A column types: passed.
- Valid pickup source-month consistency and finite numeric values: passed.

## Reproduce

Use the environment and dependency setup in the repository README, then run:

```powershell
docker compose up -d postgres
$env:PYTHONPATH = (Resolve-Path "src").Path
.\.venv\Scripts\python.exe -m taxi_dw.ingestion backfill `
  --year 2024 --start-month 1 --end-month 2
.\.venv\Scripts\python.exe -m taxi_dw.ingestion backfill `
  --year 2024 --start-month 1 --end-month 3
.\.venv\Scripts\python.exe -m taxi_dw.ingestion backfill `
  --year 2024 --start-month 1 --end-month 3

.\.venv\Scripts\dotenv.exe -f .env run -- .\.venv\Scripts\dbt.exe seed --project-dir src/dbt --profiles-dir src/dbt
.\.venv\Scripts\dotenv.exe -f .env run -- .\.venv\Scripts\dbt.exe run --project-dir src/dbt --profiles-dir src/dbt --select staging
.\.venv\Scripts\dotenv.exe -f .env run -- .\.venv\Scripts\dbt.exe test --project-dir src/dbt --profiles-dir src/dbt
```

The initial load steps above apply to a database containing January only.
If all three months already exist, every backfill invocation is skipped.

Reconcile each month:

```sql
with raw_counts as (
    select source_year, source_month, count(*) as raw_rows
    from raw.yellow_trip
    group by source_year, source_month
), classified_counts as (
    select
        source_year,
        source_month,
        count(*) filter (where dq_status = 'valid') as valid_rows,
        count(*) filter (where dq_status = 'quarantined') as quarantined_rows,
        count(*) filter (where dq_status = 'rejected') as rejected_rows,
        count(*) as staging_rows
    from staging.stg_yellow_trip
    group by source_year, source_month
)
select *
from raw_counts
full join classified_counts using (source_year, source_month)
order by source_year, source_month;
```

## Follow-up work

- Airflow and audit DQ-count write-back were added after this prototype;
  see `docs/airflow_runbook.md` for their verification and operation.
- Controlled source replacement (`replace-month`); normal backfill is
  append-or-skip only.
- Person 2 contract approval and warehouse integration.

RAW loading is incremental by month. dbt staging currently rebuilds all loaded
months; incremental dbt materialization is not implemented. Full source data
and PostgreSQL contents remain local and outside Git.
