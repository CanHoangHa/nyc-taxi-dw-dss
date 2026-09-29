"""Unit tests for the end-to-end ingestion CLI contract."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from taxi_dw.ingestion import IngestionResult, main


class IngestionCliTests(unittest.TestCase):
    @patch("taxi_dw.ingestion.ingest_validated_source")
    @patch("taxi_dw.ingestion.validate_source")
    @patch("taxi_dw.ingestion.download_source")
    def test_reports_skipped_month_with_exit_code_zero(
        self,
        download_source,
        validate_source,
        ingest_validated_source,
    ) -> None:
        validate_source.return_value = SimpleNamespace()
        ingest_validated_source.return_value = IngestionResult(
            batch_id=uuid4(),
            source_row_count=3,
            loaded_row_count=0,
            status="skipped",
        )
        output = StringIO()

        with redirect_stdout(output):
            exit_code = main(
                [
                    "run",
                    "--dataset",
                    "yellow_taxi",
                    "--year",
                    "2024",
                    "--month",
                    "1",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertIn("status=skipped", output.getvalue())
        self.assertIn("source_month=2024-01", output.getvalue())
        download_source.assert_called_once()

    @patch("taxi_dw.ingestion.download_source")
    def test_redacts_password_and_returns_nonzero_on_failure(
        self,
        download_source,
    ) -> None:
        download_source.side_effect = RuntimeError("password is demo-secret")
        output = StringIO()

        with (
            patch.dict(os.environ, {"POSTGRES_PASSWORD": "demo-secret"}),
            redirect_stderr(output),
        ):
            exit_code = main(
                ["run", "--year", "2024", "--month", "1"]
            )

        self.assertEqual(exit_code, 1)
        self.assertNotIn("demo-secret", output.getvalue())
        self.assertIn("[REDACTED]", output.getvalue())


if __name__ == "__main__":
    unittest.main()
