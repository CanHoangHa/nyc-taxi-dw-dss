"""Unit tests for bounded-memory RAW row generation."""

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from taxi_dw.raw_loader import (
    RAW_COPY_COLUMNS,
    SourceRowCountMismatch,
    iter_raw_rows,
)
from tests.parquet_fixture import create_validated_fixture


class RawRowIteratorTests(unittest.TestCase):
    def test_keeps_lineage_nulls_and_continuous_row_numbers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact = create_validated_fixture(Path(directory))
            batch_id = uuid4()
            ingested_at = datetime(2024, 1, 2, tzinfo=timezone.utc)

            rows = list(
                iter_raw_rows(
                    artifact,
                    batch_id,
                    batch_size=2,
                    ingested_at=ingested_at,
                )
            )

        row_number_index = RAW_COPY_COLUMNS.index("source_row_number")
        passenger_index = RAW_COPY_COLUMNS.index("passenger_count")
        batch_index = RAW_COPY_COLUMNS.index("batch_id")
        ingested_index = RAW_COPY_COLUMNS.index("ingested_at")
        self.assertEqual([row[row_number_index] for row in rows], [0, 1, 2])
        self.assertIsNone(rows[1][passenger_index])
        self.assertEqual({row[batch_index] for row in rows}, {batch_id})
        self.assertEqual({row[ingested_index] for row in rows}, {ingested_at})

    def test_rejects_changed_row_count(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact = create_validated_fixture(Path(directory))
            changed_artifact = replace(artifact, row_count=4)

            with self.assertRaises(SourceRowCountMismatch):
                list(iter_raw_rows(changed_artifact, uuid4(), batch_size=2))

    def test_rejects_invalid_batch_size(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact = create_validated_fixture(Path(directory))

            with self.assertRaisesRegex(ValueError, "at least 1"):
                next(iter_raw_rows(artifact, uuid4(), batch_size=0))


if __name__ == "__main__":
    unittest.main()
