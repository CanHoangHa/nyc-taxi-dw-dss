"""PostgreSQL integration tests for transactional RAW ingestion."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from taxi_dw import audit
from taxi_dw.ingestion import IngestionError, ingest_validated_source
from tests.integration.database_case import DatabaseTestCase
from tests.parquet_fixture import create_validated_fixture


@unittest.skipUnless(
    os.environ.get("RUN_DB_TESTS") == "1",
    "set RUN_DB_TESTS=1 to run PostgreSQL integration tests",
)
class RawLoaderIntegrationTests(DatabaseTestCase):
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

                with self.connect() as connection:
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
                self.delete_batches(failed_batch_id, blocking_batch_id)

    def _insert_blocking_source_row(self, artifact):
        with self.connect() as connection:
            batch_id = audit.start_batch(connection, artifact)
            audit.mark_failed(connection, batch_id, "failure drill blocker")
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
        return batch_id


if __name__ == "__main__":
    unittest.main()
