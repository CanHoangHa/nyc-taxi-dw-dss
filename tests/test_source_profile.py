"""Tests for the TLC Parquet source profiler."""

from datetime import datetime
from pathlib import Path
import tempfile
import unittest

import pyarrow as pa
import pyarrow.parquet as pq

from taxi_dw.source_profile import EXPECTED_COLUMNS, SourceProfileError, profile_parquet
from taxi_dw.source_profile_report import render_markdown


class SourceProfileTests(unittest.TestCase):
    def test_profiles_source_and_quality_indicators(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            parquet_path = root / "yellow_tripdata_2024-01.parquet"
            zone_path = root / "taxi_zone_lookup.csv"
            self._write_parquet(parquet_path)
            zone_path.write_text(
                "LocationID,Borough,Zone,service_zone\n"
                "1,Manhattan,One,Yellow Zone\n"
                "2,Queens,Two,Boro Zone\n",
                encoding="utf-8",
            )
            profile = profile_parquet(
                parquet_path,
                year=2024,
                month=1,
                zone_lookup_path=zone_path,
                batch_size=2,
                sample_size=2,
            )

        self.assertEqual(profile["parquet"]["row_count"], 3)
        self.assertEqual(profile["schema"]["missing"], [])
        self.assertEqual(profile["schema"]["unexpected"], ["new_source_field"])
        self.assertEqual(profile["quality"]["pickup_zone_null"], 1)
        self.assertEqual(profile["quality"]["pickup_zone_unmapped"], 1)
        self.assertEqual(profile["quality"]["dropoff_before_pickup"], 1)
        self.assertEqual(profile["quality"]["negative_trip_distance"], 1)
        self.assertEqual(profile["quality"]["negative_monetary_row"], 1)
        self.assertEqual(len(profile["source"]["sha256"]), 64)
        self.assertIn("new_source_field", render_markdown(profile))

    def test_reports_missing_columns(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "minimal.parquet"
            pq.write_table(pa.table({"VendorID": [1]}), path)
            profile = profile_parquet(
                path, year=2024, month=1, batch_size=1, sample_size=1
            )

        self.assertEqual(
            set(profile["schema"]["missing"]),
            set(EXPECTED_COLUMNS) - {"VendorID"},
        )

    def test_rejects_corrupt_parquet(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "corrupt.parquet"
            path.write_bytes(b"not parquet")
            with self.assertRaisesRegex(SourceProfileError, "Cannot open Parquet"):
                profile_parquet(path, year=2024, month=1)

    @staticmethod
    def _write_parquet(path: Path) -> None:
        pickup = [
            datetime(2024, 1, 1, 8),
            None,
            datetime(2023, 12, 31, 23),
        ]
        dropoff = [
            datetime(2024, 1, 1, 8, 15),
            datetime(2024, 1, 1, 9),
            datetime(2023, 12, 31, 22, 59),
        ]
        pq.write_table(
            pa.table(
                {
                    "VendorID": pa.array([1, 2, 1], type=pa.int32()),
                    "tpep_pickup_datetime": pa.array(
                        pickup, type=pa.timestamp("us")
                    ),
                    "tpep_dropoff_datetime": pa.array(
                        dropoff, type=pa.timestamp("us")
                    ),
                    "passenger_count": pa.array([1, None, 2], type=pa.int64()),
                    "trip_distance": [2.5, -1.0, 0.0],
                    "RatecodeID": pa.array([1, 1, None], type=pa.int64()),
                    "store_and_fwd_flag": ["N", "N", None],
                    "PULocationID": pa.array([1, 999, None], type=pa.int32()),
                    "DOLocationID": pa.array([2, 1, 999], type=pa.int32()),
                    "payment_type": pa.array([1, 2, 1], type=pa.int64()),
                    "fare_amount": [10.0, -2.0, 0.0],
                    "extra": [0.0, 0.0, 0.0],
                    "mta_tax": [0.5, 0.5, 0.0],
                    "tip_amount": [2.0, 0.0, 0.0],
                    "tolls_amount": [0.0, 0.0, 0.0],
                    "improvement_surcharge": [1.0, 1.0, 0.0],
                    "total_amount": [13.5, 0.0, 0.0],
                    "congestion_surcharge": [2.5, 0.0, 0.0],
                    "Airport_fee": [0.0, 0.0, None],
                    "new_source_field": ["a", "b", "c"],
                }
            ),
            path,
        )


if __name__ == "__main__":
    unittest.main()
