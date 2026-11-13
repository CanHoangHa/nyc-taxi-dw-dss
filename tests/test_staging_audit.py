"""Audit write-back must fail before updates when any batch is inconsistent."""

import unittest
from unittest.mock import MagicMock
from uuid import uuid4

from taxi_dw.staging_audit import record_classification_counts


class StagingAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = MagicMock()
        self.connection.execute.return_value.rowcount = 1
        self.batch_id = uuid4()
        self.valid_row = (self.batch_id, 3, 3, 3, 3, 1, 1, 1, "succeeded")

    def test_records_reconciled_counts_without_committing(self) -> None:
        self.connection.execute.return_value.fetchall.return_value = [self.valid_row]
        self.assertEqual(record_classification_counts(self.connection), 1)
        self.assertEqual(
            self.connection.execute.call_args.args[1], (1, 1, 1, self.batch_id)
        )
        self.connection.commit.assert_not_called()

    def test_bad_later_batch_prevents_updates_to_earlier_batch(self) -> None:
        bad_row = (uuid4(), 3, 3, 3, 2, 1, 1, 0, "succeeded")
        self.connection.execute.return_value.fetchall.return_value = [self.valid_row, bad_row]
        with self.assertRaisesRegex(ValueError, "reconciliation failed"):
            record_classification_counts(self.connection)
        self.assertEqual(self.connection.execute.call_count, 1)

    def test_empty_or_missing_staging_snapshot_is_not_recorded(self) -> None:
        for rows in ([], [(self.batch_id, 3, 3, 3, None, None, None, None, "succeeded")]):
            with self.subTest(rows=rows):
                self.connection.reset_mock()
                self.connection.execute.return_value.fetchall.return_value = rows
                with self.assertRaises(ValueError):
                    record_classification_counts(self.connection)
                self.assertEqual(self.connection.execute.call_count, 1)

    def test_unknown_status_cannot_reconcile_even_with_matching_row_count(self) -> None:
        self.connection.execute.return_value.fetchall.return_value = [
            (self.batch_id, 3, 3, 3, 3, 1, 1, 0, "succeeded")
        ]
        with self.assertRaises(ValueError):
            record_classification_counts(self.connection)
        self.assertEqual(self.connection.execute.call_count, 1)
