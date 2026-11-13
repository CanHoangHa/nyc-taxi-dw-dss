"""Integration tests for audit and RAW database constraints."""

from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone
from uuid import uuid4

import psycopg
from psycopg import errors

from taxi_dw.config import DatabaseSettings


EXPECTED_AUDIT_COLUMNS = frozenset(
    """
    batch_id dataset_name source_year source_month source_file
    source_file_sha256 started_at finished_at source_row_count
    loaded_row_count valid_count quarantined_count rejected_count status
    error_message
    """.split()
)

EXPECTED_RAW_COLUMNS = frozenset(
    """
    VendorID tpep_pickup_datetime tpep_dropoff_datetime passenger_count
    trip_distance RatecodeID store_and_fwd_flag PULocationID DOLocationID
    payment_type fare_amount extra mta_tax tip_amount tolls_amount
    improvement_surcharge total_amount congestion_surcharge Airport_fee
    batch_id source_dataset source_year source_month source_file
    source_file_sha256 source_row_number ingested_at
    """.split()
)
TEST_SOURCE_ROW_NUMBER = 9_000_000_000


@unittest.skipUnless(
    os.environ.get("RUN_DB_TESTS") == "1",
    "set RUN_DB_TESTS=1 to run PostgreSQL integration tests",
)
class IngestionSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = DatabaseSettings.from_environment()
        self.connection = psycopg.connect(
            **self.settings.as_connection_kwargs()
        )

    def tearDown(self) -> None:
        self.connection.rollback()
        self.connection.close()

    def test_expected_tables_and_source_columns_exist(self) -> None:
        rows = self.connection.execute(
            """
            SELECT table_schema, table_name, column_name, data_type
            FROM information_schema.columns
            WHERE (table_schema, table_name) IN (
                ('audit', 'etl_batch'),
                ('raw', 'yellow_trip')
            )
            """
        ).fetchall()
        columns = {
            (schema, table, column): data_type
            for schema, table, column, data_type in rows
        }
        actual_audit_columns = {
            column
            for schema, table, column in columns
            if (schema, table) == ("audit", "etl_batch")
        }
        actual_raw_columns = {
            column
            for schema, table, column in columns
            if (schema, table) == ("raw", "yellow_trip")
        }

        self.assertEqual(actual_audit_columns, EXPECTED_AUDIT_COLUMNS)
        self.assertEqual(actual_raw_columns, EXPECTED_RAW_COLUMNS)
        self.assertEqual(
            columns[("audit", "etl_batch", "batch_id")], "uuid"
        )
        self.assertEqual(
            columns[("raw", "yellow_trip", "VendorID")], "integer"
        )
        self.assertEqual(
            columns[
                ("raw", "yellow_trip", "tpep_pickup_datetime")
            ],
            "timestamp without time zone",
        )
        self.assertEqual(
            columns[("raw", "yellow_trip", "source_row_number")], "bigint"
        )

    def test_rejects_invalid_batch_status(self) -> None:
        with self.assertRaises(errors.CheckViolation):
            self._insert_batch(status="unknown")

    def test_rejects_invalid_source_month(self) -> None:
        with self.assertRaises(errors.CheckViolation):
            self._insert_batch(source_month=13)

    def test_rejects_successful_batch_with_mismatched_counts(self) -> None:
        with self.assertRaises(errors.CheckViolation):
            self._insert_batch(
                status="succeeded",
                source_row_count=10,
                loaded_row_count=9,
            )

    def test_rejects_raw_row_without_batch(self) -> None:
        with self.assertRaises(errors.ForeignKeyViolation):
            self._insert_raw_row(
                uuid4(),
                source_row_number=TEST_SOURCE_ROW_NUMBER,
            )

    def test_rejects_duplicate_source_identity(self) -> None:
        batch_id = uuid4()
        self._insert_batch(batch_id=batch_id)
        self._insert_raw_row(
            batch_id,
            source_row_number=TEST_SOURCE_ROW_NUMBER,
        )

        with self.assertRaises(errors.UniqueViolation):
            self._insert_raw_row(
                batch_id,
                source_row_number=TEST_SOURCE_ROW_NUMBER,
            )

    def _insert_batch(
        self,
        *,
        batch_id=None,
        status: str = "started",
        source_month: int = 1,
        source_row_count: int | None = None,
        loaded_row_count: int | None = None,
    ):
        finished_at = (
            None if status == "started" else datetime.now(timezone.utc)
        )
        error_message = "test failure" if status == "failed" else None
        return self.connection.execute(
            """
            INSERT INTO audit.etl_batch (
                batch_id,
                dataset_name,
                source_year,
                source_month,
                source_file,
                source_file_sha256,
                finished_at,
                source_row_count,
                loaded_row_count,
                status,
                error_message
            )
            VALUES (
                %s, 'yellow_taxi', 2024, %s,
                'yellow_tripdata_2024-01.parquet',
                %s, %s, %s, %s, %s, %s
            )
            """,
            (
                batch_id or uuid4(),
                source_month,
                "a" * 64,
                finished_at,
                source_row_count,
                loaded_row_count,
                status,
                error_message,
            ),
        )

    def _insert_raw_row(self, batch_id, *, source_row_number: int):
        return self.connection.execute(
            """
            INSERT INTO raw.yellow_trip (
                batch_id,
                source_dataset,
                source_year,
                source_month,
                source_file,
                source_file_sha256,
                source_row_number
            )
            VALUES (
                %s, 'yellow_taxi', 2024, 1,
                'yellow_tripdata_2024-01.parquet',
                %s, %s
            )
            """,
            (batch_id, "a" * 64, source_row_number),
        )


if __name__ == "__main__":
    unittest.main()
