"""PostgreSQL integration tests for monthly ingestion idempotency."""

from dataclasses import replace
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
class IdempotencyIntegrationTests(DatabaseTestCase):
    def test_same_checksum_rerun_is_skipped_without_new_raw_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact = create_validated_fixture(Path(directory), month=12)
            loaded = ingest_validated_source(
                artifact,
                settings=self.settings,
                batch_size=2,
            )
            skipped = ingest_validated_source(
                artifact,
                settings=self.settings,
                batch_size=2,
            )

        try:
            with self.connect() as connection:
                audit_rows = connection.execute(
                    """
                    SELECT status, source_row_count, loaded_row_count
                    FROM audit.etl_batch
                    WHERE batch_id = ANY(%s)
                    ORDER BY started_at
                    """,
                    ([loaded.batch_id, skipped.batch_id],),
                ).fetchall()
                raw_row = connection.execute(
                    """
                    SELECT count(*), min(source_row_number),
                           max(source_row_number), count(DISTINCT batch_id)
                    FROM raw.yellow_trip
                    WHERE batch_id = %s
                    """,
                    (loaded.batch_id,),
                ).fetchone()

            self.assertEqual(loaded.status, "succeeded")
            self.assertEqual(skipped.status, "skipped")
            self.assertEqual(skipped.loaded_row_count, 0)
            self.assertEqual(
                audit_rows,
                [("succeeded", 3, 3), ("skipped", 3, 0)],
            )
            self.assertEqual(raw_row, (3, 0, 2, 1))
        finally:
            self.delete_batches(loaded.batch_id, skipped.batch_id)

    def test_checksum_conflict_fails_without_changing_raw(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact = create_validated_fixture(Path(directory), month=10)
            loaded = ingest_validated_source(
                artifact,
                settings=self.settings,
                batch_size=2,
            )
            changed_artifact = replace(artifact, sha256="b" * 64)

            failed_batch_id = None
            try:
                with self.assertRaisesRegex(
                    IngestionError,
                    "replace-month is not implemented",
                ) as raised:
                    ingest_validated_source(
                        changed_artifact,
                        settings=self.settings,
                        batch_size=2,
                    )
                failed_batch_id = raised.exception.batch_id

                with self.connect() as connection:
                    raw_count = connection.execute(
                        "SELECT count(*) FROM raw.yellow_trip WHERE batch_id = %s",
                        (loaded.batch_id,),
                    ).fetchone()[0]
                    failed_status = connection.execute(
                        "SELECT status FROM audit.etl_batch WHERE batch_id = %s",
                        (failed_batch_id,),
                    ).fetchone()[0]

                self.assertEqual(raw_count, 3)
                self.assertEqual(failed_status, "failed")
            finally:
                self.delete_batches(failed_batch_id, loaded.batch_id)

    def test_old_failed_attempt_does_not_block_retry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact = create_validated_fixture(Path(directory), month=9)
            failed_batch_id = self._record_failed_attempt(artifact)
            loaded = ingest_validated_source(
                artifact,
                settings=self.settings,
                batch_size=2,
            )

        try:
            with self.connect() as connection:
                statuses = connection.execute(
                    """
                    SELECT status
                    FROM audit.etl_batch
                    WHERE batch_id = ANY(%s)
                    ORDER BY started_at
                    """,
                    ([failed_batch_id, loaded.batch_id],),
                ).fetchall()
                raw_count = connection.execute(
                    "SELECT count(*) FROM raw.yellow_trip WHERE batch_id = %s",
                    (loaded.batch_id,),
                ).fetchone()[0]

            self.assertEqual(statuses, [("failed",), ("succeeded",)])
            self.assertEqual(raw_count, 3)
        finally:
            self.delete_batches(failed_batch_id, loaded.batch_id)

    def _record_failed_attempt(self, artifact):
        with self.connect() as connection:
            batch_id = audit.start_batch(connection, artifact)
            audit.mark_failed(connection, batch_id, "previous test failure")
        return batch_id


if __name__ == "__main__":
    unittest.main()
