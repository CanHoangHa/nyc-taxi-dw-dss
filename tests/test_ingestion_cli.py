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

    @patch("taxi_dw.ingestion.ingest_validated_source")
    @patch("taxi_dw.ingestion.validate_source", side_effect=lambda artifact: artifact)
    @patch("taxi_dw.ingestion.download_source", side_effect=lambda source, **kwargs: source)
    def test_backfill_continues_after_skips_and_loads_months_in_order(
        self, download_source, validate_source, ingest_validated_source
    ) -> None:
        ingest_validated_source.side_effect = [
            IngestionResult(uuid4(), 3, 0, "skipped"),
            IngestionResult(uuid4(), 3, 0, "skipped"),
            IngestionResult(uuid4(), 3, 3),
        ]
        output = StringIO()
        with redirect_stdout(output):
            exit_code = main([
                "backfill", "--year", "2024",
                "--start-month", "1", "--end-month", "3",
            ])

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            [call.args[0].month for call in ingest_validated_source.call_args_list],
            [1, 2, 3],
        )
        self.assertEqual(output.getvalue().count("status=skipped"), 2)
        self.assertIn("status=succeeded", output.getvalue())
        self.assertIn("source_month=2024-03", output.getvalue())

    @patch("taxi_dw.ingestion.ingest_validated_source")
    @patch("taxi_dw.ingestion.validate_source", side_effect=lambda artifact: artifact)
    @patch("taxi_dw.ingestion.download_source", side_effect=lambda source, **kwargs: source)
    def test_backfill_stops_before_later_months_after_failure(
        self, download_source, validate_source, ingest_validated_source
    ) -> None:
        ingest_validated_source.side_effect = [
            IngestionResult(uuid4(), 3, 3),
            RuntimeError("February load failed"),
        ]
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            exit_code = main([
                "backfill", "--year", "2024",
                "--start-month", "1", "--end-month", "3",
            ])

        self.assertEqual(exit_code, 1)
        self.assertEqual(
            [call.args[0].month for call in download_source.call_args_list],
            [1, 2],
        )

    @patch("taxi_dw.ingestion.download_source")
    def test_invalid_backfill_range_fails_before_download(self, download_source) -> None:
        for start, end in [(0, 3), (3, 2), (1, 13)]:
            with self.subTest(start=start, end=end):
                with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as error:
                    main([
                        "backfill", "--year", "2024",
                        "--start-month", str(start), "--end-month", str(end),
                    ])
                self.assertEqual(error.exception.code, 2)
        download_source.assert_not_called()


if __name__ == "__main__":
    unittest.main()
