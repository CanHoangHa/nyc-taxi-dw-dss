"""Reconcile the staging snapshot and record DQ counts on loaded batches."""

from __future__ import annotations

import argparse
import os
import sys

import psycopg

from taxi_dw.db import open_connection


COUNTS_SQL = """
WITH raw_counts AS (
    SELECT batch_id, count(*) AS raw_count
    FROM raw.yellow_trip
    GROUP BY batch_id
), staging_counts AS (
    SELECT batch_id,
           count(*) AS staging_count,
           count(*) FILTER (WHERE dq_status = 'valid') AS valid_count,
           count(*) FILTER (WHERE dq_status = 'quarantined') AS quarantined_count,
           count(*) FILTER (WHERE dq_status = 'rejected') AS rejected_count
    FROM staging.stg_yellow_trip
    GROUP BY batch_id
), loaded_batches AS (
    SELECT batch_id, source_row_count, loaded_row_count, status
    FROM audit.etl_batch
    WHERE status = 'succeeded'
)
SELECT batch_id, source_row_count, loaded_row_count, raw_count, staging_count,
       valid_count, quarantined_count, rejected_count, status
FROM raw_counts
FULL JOIN staging_counts USING (batch_id)
FULL JOIN loaded_batches USING (batch_id)
ORDER BY batch_id
"""


def record_classification_counts(connection: psycopg.Connection) -> int:
    """Validate all loaded batches before any update; the caller commits."""

    rows = connection.execute(COUNTS_SQL).fetchall()
    if not rows:
        raise ValueError("No loaded batches are available for staging reconciliation")

    for row in rows:
        (
            batch_id, source_count, loaded_count, raw_count, staged_count,
            valid, quarantined, rejected, status,
        ) = row
        counts = (
            source_count, loaded_count, raw_count, staged_count,
            valid, quarantined, rejected,
        )
        if (
            batch_id is None
            or status != "succeeded"
            or any(value is None for value in counts)
            or not source_count == loaded_count == raw_count == staged_count
            or staged_count != valid + quarantined + rejected
        ):
            raise ValueError(f"RAW/staging/audit reconciliation failed for batch {batch_id}")

    for batch_id, _, _, _, _, valid, quarantined, rejected, _ in rows:
        cursor = connection.execute(
            """
            UPDATE audit.etl_batch
            SET valid_count = %s, quarantined_count = %s, rejected_count = %s
            WHERE batch_id = %s AND status = 'succeeded'
            """,
            (valid, quarantined, rejected, batch_id),
        )
        if cursor.rowcount != 1:
            raise RuntimeError(f"Loaded batch {batch_id} changed during audit write-back")
    return len(rows)


def main(arguments: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(arguments)
    try:
        with open_connection() as connection:
            updated = record_classification_counts(connection)
    except Exception as error:
        message = str(error)
        password = os.environ.get("POSTGRES_PASSWORD", "")
        if password:
            message = message.replace(password, "[REDACTED]")
        print(f"failed: {message[:2000]}", file=sys.stderr)
        return 1
    print(f"recorded_dq_counts batches={updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
