"""Validate a downloaded TLC source before database loading."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re

import pyarrow as pa
import pyarrow.parquet as pq

from taxi_dw.downloader import (
    DownloadedArtifact,
    calculate_sha256,
    download_source,
)
from taxi_dw.source import YellowTaxiSource
from taxi_dw.source_contract import EXPECTED_COLUMNS, EXPECTED_TYPES


class SourceValidationError(ValueError):
    """Raised when a source artifact violates the frozen source contract."""


@dataclass(frozen=True, slots=True)
class ValidatedSourceArtifact:
    """A source artifact proven safe to hand to the future RAW loader."""

    source: YellowTaxiSource
    path: Path
    byte_size: int
    sha256: str
    row_count: int
    row_group_count: int
    schema_fields: tuple[tuple[str, str], ...]
    validated_at: datetime


def validate_source(artifact: DownloadedArtifact) -> ValidatedSourceArtifact:
    """Validate file identity, Parquet integrity, and exact source schema."""

    path = artifact.path
    if not path.is_file():
        raise SourceValidationError(f"Source file does not exist: {path}")

    issues: list[str] = []
    actual_size = path.stat().st_size
    if path.name != artifact.source.filename:
        issues.append(
            f"filename must be {artifact.source.filename}, got {path.name}"
        )
    if actual_size == 0:
        issues.append("source file is empty")
    if actual_size != artifact.byte_size:
        issues.append(
            f"file size changed from {artifact.byte_size} to {actual_size}"
        )
    if re.fullmatch(r"[0-9a-f]{64}", artifact.sha256) is None:
        issues.append("recorded SHA-256 is not lowercase 64-character hexadecimal")

    actual_sha256 = calculate_sha256(path)
    if actual_sha256 != artifact.sha256:
        issues.append(
            f"checksum changed from {artifact.sha256} to {actual_sha256}"
        )
    if issues:
        raise SourceValidationError("; ".join(issues))

    try:
        parquet = pq.ParquetFile(path)
    except (OSError, pa.ArrowException) as error:
        raise SourceValidationError(f"Cannot open Parquet file: {error}") from error

    schema_fields = tuple(
        (field.name, str(field.type)) for field in parquet.schema_arrow
    )
    names = tuple(name for name, _ in schema_fields)
    actual_types = dict(schema_fields)
    missing = [name for name in EXPECTED_COLUMNS if name not in actual_types]
    unexpected = [name for name in names if name not in EXPECTED_TYPES]
    type_mismatches = [
        f"{name}: expected {EXPECTED_TYPES[name]}, got {actual_types[name]}"
        for name in EXPECTED_COLUMNS
        if name in actual_types and actual_types[name] != EXPECTED_TYPES[name]
    ]

    issues = []
    if parquet.metadata.num_rows == 0:
        issues.append("Parquet file contains no rows")
    if len(names) != len(set(names)):
        issues.append("Parquet schema contains duplicate field names")
    if missing:
        issues.append(f"missing fields: {', '.join(missing)}")
    if unexpected:
        issues.append(f"unexpected fields: {', '.join(unexpected)}")
    if type_mismatches:
        issues.append(f"type mismatches: {'; '.join(type_mismatches)}")
    if issues:
        raise SourceValidationError("; ".join(issues))

    return ValidatedSourceArtifact(
        source=artifact.source,
        path=path,
        byte_size=actual_size,
        sha256=actual_sha256,
        row_count=parquet.metadata.num_rows,
        row_group_count=parquet.metadata.num_row_groups,
        schema_fields=schema_fields,
        validated_at=datetime.now(timezone.utc),
    )


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True)
    parser.add_argument("--root", type=Path, default=Path("data/raw"))
    options = parser.parse_args(arguments)

    downloaded = download_source(
        YellowTaxiSource(options.year, options.month),
        root=options.root,
    )
    validated = validate_source(downloaded)
    print(
        f"validated: {validated.path} "
        f"({validated.row_count:,} rows, sha256={validated.sha256})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
