"""Orchestrate validation, audit state, and transactional RAW loading."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import sys
from uuid import UUID

import psycopg

from taxi_dw import audit
from taxi_dw.config import DatabaseSettings
from taxi_dw.db import open_connection
from taxi_dw.downloader import download_source
from taxi_dw.month_lock import locked_source_month
from taxi_dw.raw_loader import DEFAULT_BATCH_SIZE, copy_raw_rows
from taxi_dw.source import YellowTaxiSource
from taxi_dw.source_validation import ValidatedSourceArtifact, validate_source


@dataclass(frozen=True, slots=True)
class IngestionResult:
    """Summary of one successful or skipped monthly ingestion attempt."""

    batch_id: UUID
    source_row_count: int
    loaded_row_count: int
    status: str = "succeeded"


class IngestionError(RuntimeError):
    """Raised after a failed RAW transaction is recorded in audit."""

    def __init__(self, batch_id: UUID, message: str) -> None:
        super().__init__(f"Batch {batch_id} failed: {message}")
        self.batch_id = batch_id


def ingest_validated_source(
    artifact: ValidatedSourceArtifact,
    *,
    settings: DatabaseSettings | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> IngestionResult:
    """Load or skip one artifact safely under a source-month lock."""

    database_settings = settings or DatabaseSettings.from_environment()
    with open_connection(database_settings) as connection:
        with locked_source_month(connection, artifact.source):
            successful_batch = audit.find_latest_successful_batch(
                connection,
                artifact,
            )
            if successful_batch is not None:
                if successful_batch.source_file_sha256 == artifact.sha256:
                    batch_id = audit.record_skipped_batch(connection, artifact)
                    connection.commit()
                    return IngestionResult(
                        batch_id=batch_id,
                        source_row_count=artifact.row_count,
                        loaded_row_count=0,
                        status="skipped",
                    )

                batch_id = audit.start_batch(connection, artifact)
                connection.commit()
                message = (
                    "Checksum conflict for an already successful source month: "
                    f"existing={successful_batch.source_file_sha256}, "
                    f"incoming={artifact.sha256}. "
                    "replace-month is not implemented; RAW was not changed."
                )
                audit.mark_failed(connection, batch_id, message)
                connection.commit()
                raise IngestionError(batch_id, message)

            return _load_new_batch(
                connection,
                artifact,
                password=database_settings.password,
                batch_size=batch_size,
            )


def _load_new_batch(
    connection: psycopg.Connection,
    artifact: ValidatedSourceArtifact,
    *,
    password: str,
    batch_size: int,
) -> IngestionResult:
    batch_id = audit.start_batch(connection, artifact)
    connection.commit()

    try:
        loaded_row_count = copy_raw_rows(
            connection,
            artifact,
            batch_id,
            batch_size=batch_size,
        )
        if loaded_row_count != artifact.row_count:
            raise RuntimeError(
                "RAW row count mismatch: "
                f"expected {artifact.row_count}, loaded {loaded_row_count}"
            )
        audit.mark_succeeded(connection, batch_id, loaded_row_count)
        connection.commit()
    except Exception as error:
        connection.rollback()
        safe_message = _safe_error_message(error, password)
        audit.mark_failed(connection, batch_id, safe_message)
        connection.commit()
        raise IngestionError(batch_id, safe_message) from error

    return IngestionResult(
        batch_id=batch_id,
        source_row_count=artifact.row_count,
        loaded_row_count=loaded_row_count,
    )


def _safe_error_message(error: Exception, password: str) -> str:
    message = f"{type(error).__name__}: {error}"
    if password:
        message = message.replace(password, "[REDACTED]")
    return message[:2_000]


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run", help="ingest one source month")
    backfill_parser = commands.add_parser(
        "backfill", help="ingest an inclusive month range in order"
    )
    for command_parser in (run_parser, backfill_parser):
        command_parser.add_argument(
            "--dataset", choices=("yellow_taxi",), default="yellow_taxi"
        )
        command_parser.add_argument("--year", type=int, required=True)
        command_parser.add_argument("--root", type=Path, default=Path("data/raw"))
        command_parser.add_argument(
            "--batch-size", type=int, default=DEFAULT_BATCH_SIZE
        )
    run_parser.add_argument("--month", type=int, required=True)
    backfill_parser.add_argument("--start-month", type=int, required=True)
    backfill_parser.add_argument("--end-month", type=int, required=True)
    options = parser.parse_args(arguments)
    if options.batch_size < 1:
        parser.error("--batch-size must be at least 1")
    if options.command == "backfill":
        if not 1 <= options.start_month <= options.end_month <= 12:
            parser.error("month range must satisfy 1 <= start-month <= end-month <= 12")
        months = range(options.start_month, options.end_month + 1)
    else:
        months = [options.month]

    try:
        sources = [YellowTaxiSource(options.year, month) for month in months]
        for source in sources:
            artifact = validate_source(download_source(source, root=options.root))
            result = ingest_validated_source(
                artifact,
                batch_size=options.batch_size,
            )
            print(
                f"status={result.status} batch_id={result.batch_id} "
                f"dataset={options.dataset} "
                f"source_month={source.year}-{source.month:02d} "
                f"source_rows={result.source_row_count:,} "
                f"loaded_rows={result.loaded_row_count:,}",
                flush=True,
            )
    except Exception as error:
        password = os.environ.get("POSTGRES_PASSWORD", "")
        print(
            f"failed: {_safe_error_message(error, password)}",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
