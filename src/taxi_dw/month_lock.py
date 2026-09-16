"""PostgreSQL advisory locking for one source month."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

import psycopg

from taxi_dw.source import YellowTaxiSource


@contextmanager
def locked_source_month(
    connection: psycopg.Connection,
    source: YellowTaxiSource,
) -> Generator[None, None, None]:
    """Serialize ingestion attempts for one dataset, year, and month."""

    lock_partition = source.year * 100 + source.month
    connection.execute(
        "SELECT pg_advisory_lock(hashtext(%s), %s)",
        (source.dataset_name, lock_partition),
    ).fetchone()
    try:
        yield
    finally:
        connection.rollback()
        unlocked = connection.execute(
            "SELECT pg_advisory_unlock(hashtext(%s), %s)",
            (source.dataset_name, lock_partition),
        ).fetchone()
        connection.commit()
        if unlocked != (True,):
            raise RuntimeError("Could not release the source-month advisory lock")
