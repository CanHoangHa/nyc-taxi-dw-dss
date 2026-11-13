"""PostgreSQL integration test for source-month advisory locking."""

import os
import unittest

import psycopg

from taxi_dw.config import DatabaseSettings
from taxi_dw.month_lock import locked_source_month
from taxi_dw.source import YellowTaxiSource


@unittest.skipUnless(
    os.environ.get("RUN_DB_TESTS") == "1",
    "set RUN_DB_TESTS=1 to run PostgreSQL integration tests",
)
class MonthLockIntegrationTests(unittest.TestCase):
    def test_same_month_cannot_be_locked_by_two_sessions(self) -> None:
        settings = DatabaseSettings.from_environment()
        source = YellowTaxiSource(2024, 8)
        partition = source.year * 100 + source.month

        with (
            psycopg.connect(**settings.as_connection_kwargs()) as first,
            psycopg.connect(**settings.as_connection_kwargs()) as second,
        ):
            with locked_source_month(first, source):
                acquired = second.execute(
                    "SELECT pg_try_advisory_lock(hashtext(%s), %s)",
                    (source.dataset_name, partition),
                ).fetchone()
                self.assertEqual(acquired, (False,))

            acquired_after_release = second.execute(
                "SELECT pg_try_advisory_lock(hashtext(%s), %s)",
                (source.dataset_name, partition),
            ).fetchone()
            self.assertEqual(acquired_after_release, (True,))
            second.execute(
                "SELECT pg_advisory_unlock(hashtext(%s), %s)",
                (source.dataset_name, partition),
            )


if __name__ == "__main__":
    unittest.main()
