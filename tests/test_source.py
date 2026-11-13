"""Tests for monthly TLC source naming and paths."""

from pathlib import Path
import unittest

from taxi_dw.source import YellowTaxiSource


class YellowTaxiSourceTests(unittest.TestCase):
    def test_builds_official_url_filename_and_destination(self) -> None:
        source = YellowTaxiSource(2024, 1)

        self.assertEqual(source.dataset_name, "yellow_taxi")
        self.assertEqual(source.filename, "yellow_tripdata_2024-01.parquet")
        self.assertEqual(
            source.url,
            "https://d37ci6vzurychx.cloudfront.net/trip-data/"
            "yellow_tripdata_2024-01.parquet",
        )
        self.assertEqual(
            source.destination(Path("raw-root")),
            Path("raw-root/yellow/2024/01/yellow_tripdata_2024-01.parquet"),
        )

    def test_rejects_out_of_scope_year(self) -> None:
        with self.assertRaisesRegex(ValueError, "limited to 2024"):
            YellowTaxiSource(2025, 1)

    def test_rejects_invalid_month(self) -> None:
        with self.assertRaisesRegex(ValueError, "between 1 and 12"):
            YellowTaxiSource(2024, 13)


if __name__ == "__main__":
    unittest.main()
