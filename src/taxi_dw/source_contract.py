"""Frozen January 2024 Yellow Taxi source schema."""

from __future__ import annotations


EXPECTED_PARQUET_SCHEMA = (
    ("VendorID", "int32"),
    ("tpep_pickup_datetime", "timestamp[us]"),
    ("tpep_dropoff_datetime", "timestamp[us]"),
    ("passenger_count", "int64"),
    ("trip_distance", "double"),
    ("RatecodeID", "int64"),
    ("store_and_fwd_flag", "large_string"),
    ("PULocationID", "int32"),
    ("DOLocationID", "int32"),
    ("payment_type", "int64"),
    ("fare_amount", "double"),
    ("extra", "double"),
    ("mta_tax", "double"),
    ("tip_amount", "double"),
    ("tolls_amount", "double"),
    ("improvement_surcharge", "double"),
    ("total_amount", "double"),
    ("congestion_surcharge", "double"),
    ("Airport_fee", "double"),
)

EXPECTED_COLUMNS = tuple(name for name, _ in EXPECTED_PARQUET_SCHEMA)
EXPECTED_TYPES = dict(EXPECTED_PARQUET_SCHEMA)
