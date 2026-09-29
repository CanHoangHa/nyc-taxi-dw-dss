"""Bounded-memory Parquet-to-PostgreSQL RAW loading."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
from uuid import UUID

import psycopg
from psycopg import sql
import pyarrow.parquet as pq

from taxi_dw.source_contract import EXPECTED_COLUMNS
from taxi_dw.source_validation import ValidatedSourceArtifact


LINEAGE_COLUMNS = (
    "batch_id",
    "source_dataset",
    "source_year",
    "source_month",
    "source_file",
    "source_file_sha256",
    "source_row_number",
    "ingested_at",
)
RAW_COPY_COLUMNS = EXPECTED_COLUMNS + LINEAGE_COLUMNS
DEFAULT_BATCH_SIZE = 10_000

COPY_RAW_SQL = sql.SQL("COPY raw.yellow_trip ({}) FROM STDIN").format(
    sql.SQL(", ").join(sql.Identifier(name) for name in RAW_COPY_COLUMNS)
)


class SourceRowCountMismatch(RuntimeError):
    """Raised when streamed Parquet rows differ from validated metadata."""


def iter_raw_rows(
    artifact: ValidatedSourceArtifact,
    batch_id: UUID,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    ingested_at: datetime | None = None,
) -> Iterator[tuple[object, ...]]:
    """Yield source rows plus lineage without materializing the whole file."""

    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")

    loaded_at = ingested_at or datetime.now(timezone.utc)
    source_row_number = 0
    parquet = pq.ParquetFile(artifact.path)

    for record_batch in parquet.iter_batches(
        batch_size=batch_size,
        columns=list(EXPECTED_COLUMNS),
    ):
        if tuple(record_batch.schema.names) != EXPECTED_COLUMNS:
            raise ValueError("Parquet columns are not in the source contract order")

        payload_columns = [column.to_pylist() for column in record_batch.columns]
        for payload in zip(*payload_columns):
            yield (
                *payload,
                batch_id,
                artifact.source.dataset_name,
                artifact.source.year,
                artifact.source.month,
                artifact.path.name,
                artifact.sha256,
                source_row_number,
                loaded_at,
            )
            source_row_number += 1

    if source_row_number != artifact.row_count:
        raise SourceRowCountMismatch(
            "Validated source row count changed: "
            f"expected {artifact.row_count}, streamed {source_row_number}"
        )


def copy_raw_rows(
    connection: psycopg.Connection,
    artifact: ValidatedSourceArtifact,
    batch_id: UUID,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> int:
    """COPY one validated source artifact into RAW and return its row count."""

    loaded_row_count = 0
    with connection.cursor() as cursor:
        with cursor.copy(COPY_RAW_SQL) as copy:
            for row in iter_raw_rows(
                artifact,
                batch_id,
                batch_size=batch_size,
            ):
                copy.write_row(row)
                loaded_row_count += 1
    return loaded_row_count
