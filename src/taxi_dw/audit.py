"""Audit-record operations for one monthly ingestion attempt."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

import psycopg

from taxi_dw.source_validation import ValidatedSourceArtifact


class AuditStateError(RuntimeError):
    """Raised when an audit row is not in the expected state."""


@dataclass(frozen=True, slots=True)
class SuccessfulBatch:
    """The latest successful load for one source month."""

    batch_id: UUID
    source_file_sha256: str
    source_row_count: int
    loaded_row_count: int


def find_latest_successful_batch(
    connection: psycopg.Connection,
    artifact: ValidatedSourceArtifact,
) -> SuccessfulBatch | None:
    """Return the latest successful attempt for the artifact's month."""

    row = connection.execute(
        """
        SELECT batch_id, source_file_sha256,
               source_row_count, loaded_row_count
        FROM audit.etl_batch
        WHERE dataset_name = %s
          AND source_year = %s
          AND source_month = %s
          AND status = 'succeeded'
        ORDER BY finished_at DESC
        LIMIT 1
        """,
        (
            artifact.source.dataset_name,
            artifact.source.year,
            artifact.source.month,
        ),
    ).fetchone()
    if row is None:
        return None
    return SuccessfulBatch(*row)


def start_batch(
    connection: psycopg.Connection,
    artifact: ValidatedSourceArtifact,
    *,
    batch_id: UUID | None = None,
) -> UUID:
    """Insert a committed-by-caller ``started`` ingestion attempt."""

    resolved_batch_id = batch_id or uuid4()
    cursor = connection.execute(
        """
        INSERT INTO audit.etl_batch (
            batch_id,
            dataset_name,
            source_year,
            source_month,
            source_file,
            source_file_sha256,
            source_row_count,
            status
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'started')
        """,
        (
            resolved_batch_id,
            artifact.source.dataset_name,
            artifact.source.year,
            artifact.source.month,
            artifact.path.name,
            artifact.sha256,
            artifact.row_count,
        ),
    )
    if cursor.rowcount != 1:
        raise AuditStateError("Could not create the started audit attempt")
    return resolved_batch_id


def record_skipped_batch(
    connection: psycopg.Connection,
    artifact: ValidatedSourceArtifact,
    *,
    batch_id: UUID | None = None,
) -> UUID:
    """Record a same-checksum rerun without inserting RAW rows."""

    resolved_batch_id = batch_id or uuid4()
    cursor = connection.execute(
        """
        INSERT INTO audit.etl_batch (
            batch_id,
            dataset_name,
            source_year,
            source_month,
            source_file,
            source_file_sha256,
            finished_at,
            source_row_count,
            loaded_row_count,
            status
        )
        VALUES (
            %s, %s, %s, %s, %s, %s,
            clock_timestamp(), %s, 0, 'skipped'
        )
        """,
        (
            resolved_batch_id,
            artifact.source.dataset_name,
            artifact.source.year,
            artifact.source.month,
            artifact.path.name,
            artifact.sha256,
            artifact.row_count,
        ),
    )
    if cursor.rowcount != 1:
        raise AuditStateError("Could not create the skipped audit attempt")
    return resolved_batch_id


def mark_succeeded(
    connection: psycopg.Connection,
    batch_id: UUID,
    loaded_row_count: int,
) -> None:
    """Mark one started attempt as successfully loaded."""

    cursor = connection.execute(
        """
        UPDATE audit.etl_batch
        SET loaded_row_count = %s,
            status = 'succeeded',
            finished_at = clock_timestamp(),
            error_message = NULL
        WHERE batch_id = %s
          AND status = 'started'
        """,
        (loaded_row_count, batch_id),
    )
    if cursor.rowcount != 1:
        raise AuditStateError(
            f"Batch {batch_id} is missing or is not in started state"
        )


def mark_failed(
    connection: psycopg.Connection,
    batch_id: UUID,
    error_message: str,
) -> None:
    """Mark one started attempt as failed after its RAW load rolled back."""

    cursor = connection.execute(
        """
        UPDATE audit.etl_batch
        SET status = 'failed',
            finished_at = clock_timestamp(),
            error_message = %s
        WHERE batch_id = %s
          AND status = 'started'
        """,
        (error_message, batch_id),
    )
    if cursor.rowcount != 1:
        raise AuditStateError(
            f"Batch {batch_id} is missing or is not in started state"
        )
