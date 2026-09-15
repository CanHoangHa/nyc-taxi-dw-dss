"""Small PostgreSQL connection helpers shared by pipeline modules."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

import psycopg

from taxi_dw.config import DatabaseSettings


@contextmanager
def open_connection(
    settings: DatabaseSettings | None = None,
) -> Generator[psycopg.Connection, None, None]:
    """Open a transactional PostgreSQL connection and close it on exit."""

    database_settings = settings or DatabaseSettings.from_environment()
    with psycopg.connect(**database_settings.as_connection_kwargs()) as connection:
        yield connection


def database_is_ready(settings: DatabaseSettings | None = None) -> bool:
    """Return whether PostgreSQL accepts a simple query with the given settings."""

    try:
        with open_connection(settings) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                return cursor.fetchone() == (1,)
    except psycopg.Error:
        return False
