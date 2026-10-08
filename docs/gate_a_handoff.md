# Gate A Handoff - January 2024

## Status

- Handoff version: `gate-a-v1-draft`
- Pipeline commit: `24ec281` (`fix: classify numeric edge cases before staging casts`)
- Branch: `feature/ingestion-pipeline`
- Evidence collected: 2026-09-30
- Warehouse review: pending Person 2

Gate A exposes `staging.stg_yellow_trip_valid`. Its grain is one valid source
trip. Warehouse models should use this view and `staging.taxi_zone_lookup`, not
the TLC-named columns in `raw.yellow_trip`.

## Source and ingestion evidence

| Item | Value |
|---|---|
| Source file | `yellow_tripdata_2024-01.parquet` |
| SHA-256 | `c4d59da7bbc8abaeeeb1727947ee93d9891a71acb42854bd80db1571b2030510` |
| Successful batch ID | `ee53c473-cae2-444e-a842-329d1d020483` |
| Source rows | 2,964,624 |
| Loaded RAW rows | 2,964,624 |
| First source row number | 0 |
| Last source row number | 2,964,623 |

The source count, audit loaded count, and physical RAW count agree. RAW contains
one January batch and the source row-number range is complete.

## Staging reconciliation

| Status | Rows |
|---|---:|
| valid | 2,924,187 |
| quarantined | 40,381 |
| rejected | 56 |
| **classified total** | **2,964,624** |

The classified total equals the RAW count. `stg_yellow_trip_valid` contains
2,924,187 rows, 2,924,187 distinct `trip_source_key` values, and no null
`trip_source_key` values.

Top reason codes:

| Reason code | Rows |
|---|---:|
| `NEGATIVE_MONETARY_VALUE` | 37,578 |
| `EXCESSIVE_DURATION` | 1,983 |
| `NON_POSITIVE_DURATION` | 870 |
| `DROPOFF_BEFORE_PICKUP` | 56 |
| `PICKUP_OUTSIDE_SOURCE_MONTH` | 18 |

A row can have multiple reason codes. Rejection reasons take priority when dbt
assigns the single final status.

`CANONICAL_TYPE_OUT_OF_RANGE` and `NON_FINITE_NUMERIC_VALUE` both have zero
rows in January. Regression fixtures verify out-of-range casts, small negative
amounts, `NaN`, and positive and negative infinity before the canonical cast.

## Idempotent rerun evidence

The same January file was run again with the same checksum:

| Item | Value |
|---|---|
| Rerun batch ID | `96818064-5d58-4802-9b33-114f0a9f9b6e` |
| Status | `skipped` |
| Source rows | 2,964,624 |
| Newly loaded rows | 0 |
| RAW rows after rerun | 2,964,624 |

The changed-checksum path is covered by the PostgreSQL integration test: it
fails before modifying the successful RAW month because `replace-month` is not
implemented yet.

## Verification result

- dbt models: 2 passed, 0 failed
- dbt tests: 24 passed, 0 failed (23 data tests and 1 unit test)
- Python tests: 45 passed, 0 failed, including PostgreSQL integration tests
- Taxi Zone Lookup seed: 265 rows with unique, non-null `location_id`
- Gate A column-name/type contract test: passed

## Reproduce

From the repository root, with Docker running and `.env` configured:

```powershell
docker compose up -d postgres

$env:PYTHONPATH = (Resolve-Path "src").Path
.\.venv\Scripts\python.exe -m taxi_dw.ingestion run `
  --dataset yellow_taxi --year 2024 --month 1

.\.venv\Scripts\dotenv.exe -f .env run -- `
  .\.venv\Scripts\dbt.exe seed `
  --project-dir src/dbt --profiles-dir src/dbt
.\.venv\Scripts\dotenv.exe -f .env run -- `
  .\.venv\Scripts\dbt.exe run `
  --project-dir src/dbt --profiles-dir src/dbt --select staging
.\.venv\Scripts\dotenv.exe -f .env run -- `
  .\.venv\Scripts\dbt.exe test `
  --project-dir src/dbt --profiles-dir src/dbt
```

Run this reconciliation query:

```sql
select
    (select count(*) from raw.yellow_trip
     where source_year = 2024 and source_month = 1) as raw_count,
    count(*) filter (where dq_status = 'valid') as valid_count,
    count(*) filter (where dq_status = 'quarantined') as quarantined_count,
    count(*) filter (where dq_status = 'rejected') as rejected_count,
    count(*) as classified_count
from staging.stg_yellow_trip
where source_year = 2024 and source_month = 1;
```

## Person 2 review checklist

- [ ] Follow the README database setup from a separate checkout.
- [ ] Run `select * from staging.stg_yellow_trip_valid limit 10`.
- [ ] Confirm the canonical columns and types satisfy dimensions and
      `fact_trip`.
- [ ] Confirm the grain is one valid source trip.
- [ ] Confirm warehouse models do not need `raw.yellow_trip`.
- [ ] Record requested contract changes, or approve `gate-a-v1`.

After this review passes, update `docs/data_contracts.md` from draft to approved
in a small review commit.

## Known limitations

- This handoff records January 2024 evidence. The subsequent January-March
  prototype is documented in `docs/profiles/yellow_tripdata_2024_q1_dq.md`.
- `replace-month` is intentionally not implemented; a changed checksum fails
  safely.
- Airflow was added after this January handoff; see `docs/airflow_runbook.md`.
- No upper trip-distance threshold has been approved.
- Classification counts were originally held in this evidence package.
  The subsequent Airflow pipeline populates them on successful RAW batches
  after staging tests and reconciliation pass.
- Runbook verification on another group member's machine and Person 2 interface
  approval are still pending.

## Gate A definition of done

- [x] January downloaded and validated from the official source.
- [x] Checksum and source metadata recorded in audit.
- [x] Transactional RAW load leaves no partial batch.
- [x] Same-checksum rerun does not duplicate RAW.
- [x] Changed-checksum rerun fails safely.
- [x] `trip_source_key` is unique and non-null.
- [x] Every record has exactly one DQ status.
- [x] Numeric anomalies are classified before guarded canonical casts.
- [x] Valid pickups fall within their declared source month.
- [x] RAW count equals valid plus quarantined plus rejected.
- [x] `stg_yellow_trip_valid` matches the implemented contract.
- [x] Unit, integration, and dbt tests pass.
- [ ] Runbook verified from another member's checkout.
- [ ] Person 2 reviewed and approved the interface.
