"""Orchestrate validation, audit state, and transactional RAW loading."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from taxi_dw import audit
from taxi_dw.config import DatabaseSettings
from taxi_dw.db import open_connection
from taxi_dw.downloader import download_source
from taxi_dw.raw_loader import DEFAULT_BATCH_SIZE, copy_raw_rows
from taxi_dw.source import YellowTaxiSource
from taxi_dw.source_validation import ValidatedSourceArtifact, validate_source


@dataclass(frozen=True, slots=True)
class IngestionResult:
    """Summary of one successful monthly RAW load."""

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
    """Load one validated artifact with no visible partial RAW batch."""

    database_settings = settings or DatabaseSettings.from_environment()
    with open_connection(database_settings) as connection:
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
            safe_message = _safe_error_message(error, database_settings.password)
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
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True)
    parser.add_argument("--root", type=Path, default=Path("data/raw"))
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    options = parser.parse_args(arguments)

    source = YellowTaxiSource(options.year, options.month)
    artifact = validate_source(download_source(source, root=options.root))
    result = ingest_validated_source(
        artifact,
        batch_size=options.batch_size,
    )
    print(
        f"{result.status}: batch_id={result.batch_id} "
        f"source_rows={result.source_row_count:,} "
        f"loaded_rows={result.loaded_row_count:,}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
