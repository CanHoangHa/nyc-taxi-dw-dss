"""Unit tests for source-month advisory locking."""

import unittest
from unittest.mock import MagicMock, call

from taxi_dw.month_lock import locked_source_month
from taxi_dw.source import YellowTaxiSource


class MonthLockTests(unittest.TestCase):
    def test_acquires_and_releases_the_month_lock(self) -> None:
        connection = MagicMock()
        connection.execute.return_value.fetchone.side_effect = [None, (True,)]
        source = YellowTaxiSource(2024, 3)

        with locked_source_month(connection, source):
            pass

        self.assertEqual(
            connection.execute.call_args_list,
            [
                call(
                    "SELECT pg_advisory_lock(hashtext(%s), %s)",
                    ("yellow_taxi", 202403),
                ),
                call(
                    "SELECT pg_advisory_unlock(hashtext(%s), %s)",
                    ("yellow_taxi", 202403),
                ),
            ],
        )
        connection.rollback.assert_called_once_with()
        connection.commit.assert_called_once_with()

    def test_releases_lock_when_ingestion_raises(self) -> None:
        connection = MagicMock()
        connection.execute.return_value.fetchone.side_effect = [None, (True,)]

        with self.assertRaisesRegex(RuntimeError, "load failed"):
            with locked_source_month(
                connection,
                YellowTaxiSource(2024, 4),
            ):
                raise RuntimeError("load failed")

        connection.rollback.assert_called_once_with()
        connection.commit.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
