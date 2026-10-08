"""Exercise real audit constraints in an isolated, disposable test database."""

import os
from pathlib import Path
import unittest
from uuid import uuid4

import psycopg
from psycopg import sql

from taxi_dw.config import DatabaseSettings
from taxi_dw.staging_audit import record_classification_counts


@unittest.skipUnless(os.environ.get("RUN_DB_TESTS") == "1", "set RUN_DB_TESTS=1")
class StagingAuditIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = DatabaseSettings.from_environment()
        cls.database_name = "taxi_staging_audit_test_" + uuid4().hex
        with psycopg.connect(**cls.settings.as_connection_kwargs(), autocommit=True) as connection:
            connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(cls.database_name)))
        cls.test_settings = dict(cls.settings.as_connection_kwargs(), dbname=cls.database_name)
        try:
            with psycopg.connect(**cls.test_settings, autocommit=True) as connection:
                root = Path(__file__).resolve().parents[2]
                for filename in ("001_create_schemas.sql", "002_create_ingestion_tables.sql"):
                    script = (root / "sql" / filename).read_text(encoding="utf-8")
                    connection.execute(script.replace("\\set ON_ERROR_STOP on", ""))
                connection.execute("CREATE TABLE staging.stg_yellow_trip (batch_id uuid, dq_status text)")
        except Exception:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls) -> None:
        if not cls.database_name.startswith("taxi_staging_audit_test_"):
            raise ValueError("Unexpected test database name")
        with psycopg.connect(**cls.settings.as_connection_kwargs(), autocommit=True) as connection:
            connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(cls.database_name)))

    def setUp(self) -> None:
        self.connection = psycopg.connect(**self.test_settings)
        self.loaded_id, self.skipped_id = uuid4(), uuid4()
        for batch_id, status, loaded_rows in (
            (self.loaded_id, "succeeded", 3), (self.skipped_id, "skipped", 0)
        ):
            self.connection.execute(
                """INSERT INTO audit.etl_batch (
                    batch_id, dataset_name, source_year, source_month,
                    source_file, source_file_sha256, status, finished_at,
                    source_row_count, loaded_row_count
                ) VALUES (%s, 'yellow_taxi', 2024, 1, 'yellow_tripdata_2024-01.parquet',
                          %s, %s, clock_timestamp(), 3, %s)""",
                (batch_id, "a" * 64, status, loaded_rows),
            )
        self.connection.execute(
            """INSERT INTO raw.yellow_trip (
                batch_id, source_dataset, source_year, source_month,
                source_file, source_file_sha256, source_row_number
            ) SELECT %s, 'yellow_taxi', 2024, 1, 'yellow_tripdata_2024-01.parquet',
                     %s, row_number FROM generate_series(0, 2) AS row_number""",
            (self.loaded_id, "a" * 64),
        )
        for status in ("valid", "quarantined", "rejected"):
            self.connection.execute(
                "INSERT INTO staging.stg_yellow_trip VALUES (%s, %s)", (self.loaded_id, status)
            )

    def tearDown(self) -> None:
        self.connection.rollback()
        self.connection.close()

    def test_counts_belong_to_loaded_batch_even_after_a_skipped_rerun(self) -> None:
        self.assertEqual(record_classification_counts(self.connection), 1)
        self.assertEqual(record_classification_counts(self.connection), 1)
        rows = self.connection.execute(
            "SELECT status, valid_count, quarantined_count, rejected_count FROM audit.etl_batch ORDER BY status"
        ).fetchall()
        self.assertEqual(rows, [("skipped", None, None, None), ("succeeded", 1, 1, 1)])
        self.assertEqual(self.connection.execute("SELECT count(*) FROM raw.yellow_trip").fetchone(), (3,))

    def test_incomplete_snapshot_does_not_write_counts(self) -> None:
        self.connection.execute("DELETE FROM staging.stg_yellow_trip WHERE dq_status = 'rejected'")
        with self.assertRaisesRegex(ValueError, "reconciliation failed"):
            record_classification_counts(self.connection)
        self.assertEqual(
            self.connection.execute("SELECT valid_count FROM audit.etl_batch WHERE batch_id = %s", (self.loaded_id,)).fetchone(),
            (None,),
        )

    def test_unclassified_row_does_not_write_counts(self) -> None:
        self.connection.execute("UPDATE staging.stg_yellow_trip SET dq_status = 'unknown' WHERE dq_status = 'rejected'")
        with self.assertRaisesRegex(ValueError, "reconciliation failed"):
            record_classification_counts(self.connection)
