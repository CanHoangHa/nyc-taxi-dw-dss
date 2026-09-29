"""Shared PostgreSQL helpers for integration test cases."""

import unittest

import psycopg

from taxi_dw.config import DatabaseSettings


class DatabaseTestCase(unittest.TestCase):
    """Base case with project database connection and batch cleanup helpers."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = DatabaseSettings.from_environment()

    def connect(self):
        return psycopg.connect(**self.settings.as_connection_kwargs())

    def delete_batches(self, *batch_ids) -> None:
        existing_ids = [batch_id for batch_id in batch_ids if batch_id]
        if not existing_ids:
            return
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM raw.yellow_trip WHERE batch_id = ANY(%s)",
                (existing_ids,),
            )
            connection.execute(
                "DELETE FROM audit.etl_batch WHERE batch_id = ANY(%s)",
                (existing_ids,),
            )
