"""Small contract-valid Parquet fixtures shared by ingestion tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from taxi_dw.downloader import DownloadedArtifact, calculate_sha256
from taxi_dw.source import YellowTaxiSource
from taxi_dw.source_contract import EXPECTED_PARQUET_SCHEMA
from taxi_dw.source_validation import ValidatedSourceArtifact, validate_source


ARROW_TYPES = {
    "int32": pa.int32(),
    "int64": pa.int64(),
    "double": pa.float64(),
    "large_string": pa.large_string(),
    "timestamp[us]": pa.timestamp("us"),
}


def create_validated_fixture(
    root: Path,
    *,
    month: int = 1,
    row_count: int = 3,
) -> ValidatedSourceArtifact:
    """Write and validate a tiny Yellow Taxi source artifact."""

    source = YellowTaxiSource(2024, month)
    path = source.destination(root)
    path.parent.mkdir(parents=True)
    schema = pa.schema(
        (name, ARROW_TYPES[type_name])
        for name, type_name in EXPECTED_PARQUET_SCHEMA
    )
    data = {
        field.name: _values_for(field.name, field.type, row_count)
        for field in schema
    }
    table = pa.Table.from_pydict(data, schema=schema)
    pq.write_table(table, path, row_group_size=2)
    downloaded = DownloadedArtifact(
        source=source,
        path=path.resolve(),
        byte_size=path.stat().st_size,
        sha256=calculate_sha256(path),
        downloaded=True,
        observed_at=datetime.now(timezone.utc),
    )
    return validate_source(downloaded)


def _values_for(
    field_name: str,
    data_type: pa.DataType,
    row_count: int,
) -> list[object]:
    if field_name == "passenger_count":
        return [None if index == 1 else index + 1 for index in range(row_count)]
    if pa.types.is_timestamp(data_type):
        start = datetime(2024, 1, 1, 12)
        return [start + timedelta(minutes=index) for index in range(row_count)]
    if pa.types.is_string(data_type) or pa.types.is_large_string(data_type):
        return ["N" for _ in range(row_count)]
    if pa.types.is_floating(data_type):
        return [float(index + 1) for index in range(row_count)]
    return [index + 1 for index in range(row_count)]
