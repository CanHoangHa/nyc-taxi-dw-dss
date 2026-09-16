"""Unit tests for ingestion audit state operations."""

from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock
from uuid import uuid4

from taxi_dw.audit import AuditStateError, mark_failed, mark_succeeded, start_batch
from taxi_dw.source import YellowTaxiSource


class AuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = MagicMock()
        self.connection.execute.return_value.rowcount = 1
        self.artifact = SimpleNamespace(
            source=YellowTaxiSource(2024, 1),
            path=Path("yellow_tripdata_2024-01.parquet"),
            sha256="a" * 64,
            row_count=3,
        )

    def test_start_batch_maps_source_metadata(self) -> None:
        batch_id = uuid4()

        result = start_batch(
            self.connection,
            self.artifact,
            batch_id=batch_id,
        )

        parameters = self.connection.execute.call_args.args[1]
        self.assertEqual(result, batch_id)
        self.assertEqual(
            parameters,
            (
                batch_id,
                "yellow_taxi",
                2024,
                1,
                "yellow_tripdata_2024-01.parquet",
                "a" * 64,
                3,
            ),
        )

    def test_mark_operations_leave_commit_to_orchestrator(self) -> None:
        batch_id = uuid4()

        mark_succeeded(self.connection, batch_id, 3)
        mark_failed(self.connection, batch_id, "copy failed")

        self.connection.commit.assert_not_called()
        self.connection.rollback.assert_not_called()

    def test_rejects_update_when_batch_is_not_started(self) -> None:
        self.connection.execute.return_value.rowcount = 0

        with self.assertRaisesRegex(AuditStateError, "not in started state"):
            mark_succeeded(self.connection, uuid4(), 3)


if __name__ == "__main__":
    unittest.main()
