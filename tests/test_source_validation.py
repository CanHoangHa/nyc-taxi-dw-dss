"""Tests for strict TLC source artifact validation."""

from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

import pyarrow as pa
import pyarrow.parquet as pq

from taxi_dw.downloader import DownloadedArtifact, calculate_sha256
from taxi_dw.source import YellowTaxiSource
from taxi_dw.source_contract import EXPECTED_PARQUET_SCHEMA
from taxi_dw.source_validation import SourceValidationError, validate_source


ARROW_TYPES = {
    "int32": pa.int32(),
    "int64": pa.int64(),
    "double": pa.float64(),
    "large_string": pa.large_string(),
    "timestamp[us]": pa.timestamp("us"),
}


class SourceValidationTests(unittest.TestCase):
    def test_accepts_exact_contract_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact = self._artifact(Path(directory))
            validated = validate_source(artifact)

        self.assertEqual(validated.row_count, 1)
        self.assertEqual(validated.sha256, artifact.sha256)
        self.assertEqual(len(validated.schema_fields), 19)

    def test_rejects_missing_required_field(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact = self._artifact(
                Path(directory), excluded={"Airport_fee"}
            )
            with self.assertRaisesRegex(
                SourceValidationError, "missing fields: Airport_fee"
            ):
                validate_source(artifact)

    def test_rejects_unexpected_field(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact = self._artifact(Path(directory), extra_field=True)
            with self.assertRaisesRegex(
                SourceValidationError, "unexpected fields: new_field"
            ):
                validate_source(artifact)

    def test_rejects_wrong_physical_type(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact = self._artifact(
                Path(directory), vendor_type=pa.int64()
            )
            with self.assertRaisesRegex(
                SourceValidationError,
                "VendorID: expected int32, got int64",
            ):
                validate_source(artifact)

    def test_rejects_empty_parquet(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact = self._artifact(Path(directory), row_count=0)
            with self.assertRaisesRegex(
                SourceValidationError, "contains no rows"
            ):
                validate_source(artifact)

    def test_rejects_corrupt_parquet(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = YellowTaxiSource(2024, 1)
            path = source.destination(root)
            path.parent.mkdir(parents=True)
            path.write_bytes(b"not parquet")
            artifact = self._downloaded_artifact(source, path)

            with self.assertRaisesRegex(
                SourceValidationError, "Cannot open Parquet"
            ):
                validate_source(artifact)

    def test_rejects_file_changed_after_download(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact = self._artifact(Path(directory))
            artifact.path.write_bytes(artifact.path.read_bytes() + b"changed")

            with self.assertRaisesRegex(
                SourceValidationError, "file size changed"
            ):
                validate_source(artifact)

    def _artifact(
        self,
        root: Path,
        *,
        excluded: set[str] | None = None,
        extra_field: bool = False,
        vendor_type: pa.DataType = pa.int32(),
        row_count: int = 1,
    ) -> DownloadedArtifact:
        source = YellowTaxiSource(2024, 1)
        path = source.destination(root)
        path.parent.mkdir(parents=True)
        excluded = excluded or set()

        fields = [
            (
                name,
                vendor_type
                if name == "VendorID"
                else ARROW_TYPES[type_name],
            )
            for name, type_name in EXPECTED_PARQUET_SCHEMA
            if name not in excluded
        ]
        if extra_field:
            fields.append(("new_field", pa.string()))

        schema = pa.schema(fields)
        row = {
            field.name: self._value_for(field.type)
            for field in schema
        }
        table = pa.Table.from_pylist(
            [row] if row_count else [],
            schema=schema,
        )
        pq.write_table(table, path)
        return self._downloaded_artifact(source, path)

    @staticmethod
    def _downloaded_artifact(
        source: YellowTaxiSource, path: Path
    ) -> DownloadedArtifact:
        return DownloadedArtifact(
            source=source,
            path=path.resolve(),
            byte_size=path.stat().st_size,
            sha256=calculate_sha256(path),
            downloaded=True,
            observed_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def _value_for(data_type: pa.DataType):
        if pa.types.is_timestamp(data_type):
            return datetime(2024, 1, 1, 12)
        if pa.types.is_string(data_type) or pa.types.is_large_string(data_type):
            return "N"
        if pa.types.is_floating(data_type):
            return 1.0
        return 1


if __name__ == "__main__":
    unittest.main()
