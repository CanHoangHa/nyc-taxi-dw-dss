# Yellow Taxi 2024-01 Source Profile

## Source

- URL: https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2024-01.parquet
- File: yellow_tripdata_2024-01.parquet
- Size: 49,961,641 bytes
- SHA-256: c4d59da7bbc8abaeeeb1727947ee93d9891a71acb42854bd80db1571b2030510
- Profiled at (UTC): 2026-09-16T05:17:24.366443+00:00
- Rows: 2,964,624
- Row groups: 3
- Created by: parquet-cpp-arrow version 14.0.2
- Zone lookup SHA-256: 1a99e105092230f8620f301edcca7f80d3080642ff404d28ed957d3fa222c8ed
- Zone IDs: 265

The Parquet file stays under Git-ignored data/raw.

## Schema

| # | Field | Arrow type | Nulls | Proposed RAW type |
|---:|---|---|---:|---|
| 1 | VendorID | int32 | 0 | integer |
| 2 | tpep_pickup_datetime | timestamp[us] | 0 | timestamp without time zone |
| 3 | tpep_dropoff_datetime | timestamp[us] | 0 | timestamp without time zone |
| 4 | passenger_count | int64 | 140,162 | bigint |
| 5 | trip_distance | double | 0 | double precision |
| 6 | RatecodeID | int64 | 140,162 | bigint |
| 7 | store_and_fwd_flag | large_string | 140,162 | text |
| 8 | PULocationID | int32 | 0 | integer |
| 9 | DOLocationID | int32 | 0 | integer |
| 10 | payment_type | int64 | 0 | bigint |
| 11 | fare_amount | double | 0 | double precision |
| 12 | extra | double | 0 | double precision |
| 13 | mta_tax | double | 0 | double precision |
| 14 | tip_amount | double | 0 | double precision |
| 15 | tolls_amount | double | 0 | double precision |
| 16 | improvement_surcharge | double | 0 | double precision |
| 17 | total_amount | double | 0 | double precision |
| 18 | congestion_surcharge | double | 140,162 | double precision |
| 19 | Airport_fee | double | 140,162 | double precision |

- Missing fields: none
- Unexpected fields: none

## Timestamp coverage

- Pickup: 2002-12-31 22:59:39 to 2024-02-01 00:01:15
- Drop-off: 2002-12-31 23:05:41 to 2024-02-02 13:56:52

## Numeric profile

Quantiles use a deterministic bounded sample; counts and bounds are exact.

| Metric | Count | Min | Sample p50 | Sample p95 | Sample p99 | Max |
|---|---:|---:|---:|---:|---:|---:|
| passenger_count | 2,824,462 | 0.0000 | 1.0000 | 3.0000 | 5.0000 | 9.0000 |
| trip_distance | 2,964,624 | 0.0000 | 1.6900 | 13.8800 | 19.9300 | 312,722.3000 |
| total_amount | 2,964,624 | -900.0000 | 20.1200 | 80.2300 | 103.3600 | 5,000.0000 |
| trip_duration_minutes | 2,964,624 | -13.5667 | 11.6833 | 38.0500 | 60.4500 | 9,455.4000 |

## Initial quality indicators

| Indicator | Rows |
|---|---:|
| pickup_zone_null | 0 (0.0000%) |
| pickup_zone_unmapped | 0 (0.0000%) |
| dropoff_zone_null | 0 (0.0000%) |
| dropoff_zone_unmapped | 0 (0.0000%) |
| pickup_outside_month | 18 (0.0006%) |
| dropoff_before_pickup | 56 (0.0019%) |
| non_positive_duration | 870 (0.0293%) |
| negative_trip_distance | 0 (0.0000%) |
| negative_monetary_row | 37,578 (1.2675%) |

Thresholds for unusually long duration and distance remain a team decision.
Negative monetary rows remain traceable and are not silently removed.

## Reproduce

~~~powershell
$env:PYTHONPATH = (Resolve-Path "src").Path
.\.venv\Scripts\python.exe -m taxi_dw.source_profile --path data/raw/yellow/2024/01/yellow_tripdata_2024-01.parquet --year 2024 --month 1 --zone-lookup data/reference/taxi_zone_lookup.csv --output docs/profiles/yellow_tripdata_2024_01.md
~~~
