"""PostgreSQL integration tests for transactional RAW ingestion."""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

import psycopg

from taxi_dw import audit
from taxi_dw.config import DatabaseSettings
from taxi_dw.ingestion import IngestionError, ingest_validated_source
from tests.parquet_fixture import create_validated_fixture


@unittest.skipUnless(
    os.environ.get("RUN_DB_TESTS") == "1",
    "set RUN_DB_TESTS=1 to run PostgreSQL integration tests",
)
class RawLoaderIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = DatabaseSettings.from_environment()

    def test_loads_fixture_with_reconciled_audit_and_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact = create_validated_fixture(Path(directory), month=12)
            result = ingest_validated_source(
                artifact,
                settings=self.settings,
                batch_size=2,
            )

        try:
            with self._connect() as connection:
                audit_row = connection.execute(
                    """
                    SELECT status, source_row_count, loaded_row_count
                    FROM audit.etl_batch
                    WHERE batch_id = %s
                    """,
                    (result.batch_id,),
                ).fetchone()
                raw_row = connection.execute(
                    """
                    SELECT count(*), min(source_row_number),
                           max(source_row_number), count(DISTINCT batch_id)
                    FROM raw.yellow_trip
                    WHERE batch_id = %s
                    """,
                    (result.batch_id,),
                ).fetchone()

            self.assertEqual(audit_row, ("succeeded", 3, 3))
            self.assertEqual(raw_row, (3, 0, 2, 1))
        finally:
            self._delete_batches(result.batch_id)

    def test_copy_failure_rolls_back_raw_and_records_failed_audit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact = create_validated_fixture(Path(directory), month=11)

            blocking_batch_id = self._insert_blocking_source_row(artifact)
            failed_batch_id = None
            try:
                with self.assertRaises(IngestionError) as raised:
                    ingest_validated_source(
                        artifact,
                        settings=self.settings,
                        batch_size=2,
                    )
                failed_batch_id = raised.exception.batch_id

                with self._connect() as connection:
                    raw_count = connection.execute(
                        """
                        SELECT count(*)
                        FROM raw.yellow_trip
                        WHERE batch_id = %s
                        """,
                        (failed_batch_id,),
                    ).fetchone()[0]
                    status, error_message = connection.execute(
                        """
                        SELECT status, error_message
                        FROM audit.etl_batch
                        WHERE batch_id = %s
                        """,
                        (failed_batch_id,),
                    ).fetchone()

                self.assertEqual(raw_count, 0)
                self.assertEqual(status, "failed")
                self.assertIn("UniqueViolation", error_message)
                self.assertNotIn(self.settings.password, error_message)
            finally:
                self._delete_batches(failed_batch_id, blocking_batch_id)

    def _insert_blocking_source_row(self, artifact):
        with self._connect() as connection:
            batch_id = audit.start_batch(
                connection,
                replace(artifact, row_count=1),
            )
            connection.execute(
                """
                INSERT INTO raw.yellow_trip (
                    batch_id, source_dataset, source_year, source_month,
                    source_file, source_file_sha256, source_row_number
                )
                VALUES (%s, 'yellow_taxi', 2024, %s, %s, %s, 1)
                """,
                (
                    batch_id,
                    artifact.source.month,
                    artifact.path.name,
                    artifact.sha256,
                ),
            )
            audit.mark_succeeded(connection, batch_id, 1)
        return batch_id

    def _delete_batches(self, *batch_ids) -> None:
        existing_ids = [batch_id for batch_id in batch_ids if batch_id]
        if not existing_ids:
            return
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM raw.yellow_trip WHERE batch_id = ANY(%s)",
                (existing_ids,),
            )
            connection.execute(
                "DELETE FROM audit.etl_batch WHERE batch_id = ANY(%s)",
                (existing_ids,),
            )

    def _connect(self):
        return psycopg.connect(**self.settings.as_connection_kwargs())


if __name__ == "__main__":
    unittest.main()
