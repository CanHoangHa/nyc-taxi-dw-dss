"""Profile a TLC Yellow Taxi Parquet file in bounded-memory batches."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import math
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from taxi_dw.source_profile_report import render_markdown


EXPECTED_COLUMNS = (
    "VendorID",
    "tpep_pickup_datetime",
    "tpep_dropoff_datetime",
    "passenger_count",
    "trip_distance",
    "RatecodeID",
    "store_and_fwd_flag",
    "PULocationID",
    "DOLocationID",
    "payment_type",
    "fare_amount",
    "extra",
    "mta_tax",
    "tip_amount",
    "tolls_amount",
    "improvement_surcharge",
    "total_amount",
    "congestion_surcharge",
    "Airport_fee",
)

MONETARY_COLUMNS = EXPECTED_COLUMNS[10:]


class SourceProfileError(RuntimeError):
    """Raised when source profiling cannot continue."""


def profile_parquet(
    path: Path,
    *,
    year: int,
    month: int,
    zone_lookup_path: Path | None = None,
    batch_size: int = 50_000,
    sample_size: int = 100_000,
) -> dict[str, Any]:
    """Collect schema, distribution, and initial quality facts."""

    if year < 2009 or month not in range(1, 13):
        raise ValueError("year must be at least 2009 and month must be 1-12")
    if batch_size < 1 or sample_size < 1:
        raise ValueError("batch_size and sample_size must be positive")
    if not path.is_file() or path.stat().st_size == 0:
        raise SourceProfileError(f"Missing or empty source file: {path}")

    try:
        parquet = pq.ParquetFile(path)
    except (OSError, pa.ArrowException) as error:
        raise SourceProfileError(f"Cannot open Parquet file {path}: {error}") from error

    names = tuple(parquet.schema_arrow.names)
    row_count = parquet.metadata.num_rows
    stride = max(1, math.ceil(row_count / sample_size))
    nulls = {name: 0 for name in names}
    metrics = {
        name: {"count": 0, "min": None, "max": None, "sample": []}
        for name in (
            "passenger_count",
            "trip_distance",
            "total_amount",
            "trip_duration_minutes",
        )
    }
    quality = {
        "pickup_zone_null": 0,
        "pickup_zone_unmapped": 0,
        "dropoff_zone_null": 0,
        "dropoff_zone_unmapped": 0,
        "pickup_outside_month": 0,
        "dropoff_before_pickup": 0,
        "non_positive_duration": 0,
        "negative_trip_distance": 0,
        "negative_monetary_row": 0,
    }
    zone_ids = _read_zone_ids(zone_lookup_path) if zone_lookup_path else None
    month_start = datetime(year, month, 1)
    month_end = (
        datetime(year + 1, 1, 1)
        if month == 12
        else datetime(year, month + 1, 1)
    )
    pickup_min = pickup_max = dropoff_min = dropoff_max = None
    processed = 0

    for batch in parquet.iter_batches(batch_size=batch_size):
        columns = {
            name: batch.column(batch.schema.get_field_index(name))
            for name in batch.schema.names
        }
        for name, column in columns.items():
            nulls[name] += column.null_count

        for name in ("passenger_count", "trip_distance", "total_amount"):
            if name in columns:
                _update_metric(metrics[name], columns[name].to_pylist(), processed, stride)

        pickups = _values(columns, "tpep_pickup_datetime", batch.num_rows)
        dropoffs = _values(columns, "tpep_dropoff_datetime", batch.num_rows)
        durations: list[float | None] = []
        for pickup, dropoff in zip(pickups, dropoffs, strict=True):
            if pickup is not None:
                pickup_min = pickup if pickup_min is None else min(pickup_min, pickup)
                pickup_max = pickup if pickup_max is None else max(pickup_max, pickup)
                quality["pickup_outside_month"] += int(
                    not month_start <= pickup < month_end
                )
            if dropoff is not None:
                dropoff_min = (
                    dropoff if dropoff_min is None else min(dropoff_min, dropoff)
                )
                dropoff_max = (
                    dropoff if dropoff_max is None else max(dropoff_max, dropoff)
                )

            duration = (
                (dropoff - pickup).total_seconds() / 60
                if pickup is not None and dropoff is not None
                else None
            )
            durations.append(duration)
            if duration is not None:
                quality["dropoff_before_pickup"] += int(duration < 0)
                quality["non_positive_duration"] += int(duration <= 0)

        _update_metric(metrics["trip_duration_minutes"], durations, processed, stride)
        _count_zones(
            _values(columns, "PULocationID", batch.num_rows),
            zone_ids,
            quality,
            "pickup",
        )
        _count_zones(
            _values(columns, "DOLocationID", batch.num_rows),
            zone_ids,
            quality,
            "dropoff",
        )

        if "trip_distance" in columns:
            quality["negative_trip_distance"] += _count_true(
                pc.less(columns["trip_distance"], 0)
            )

        negative_money: pa.Array | None = None
        for name in MONETARY_COLUMNS:
            if name in columns:
                mask = pc.fill_null(pc.less(columns[name], 0), False)
                negative_money = (
                    mask if negative_money is None else pc.or_(negative_money, mask)
                )
        if negative_money is not None:
            quality["negative_monetary_row"] += _count_true(negative_money)
        processed += batch.num_rows

    if processed != row_count:
        raise SourceProfileError(
            f"Read {processed:,} rows but metadata reports {row_count:,}"
        )
    for metric in metrics.values():
        _finish_metric(metric)

    expected = set(EXPECTED_COLUMNS)
    return {
        "source": {
            "url": (
                "https://d37ci6vzurychx.cloudfront.net/trip-data/"
                f"yellow_tripdata_{year}-{month:02d}.parquet"
            ),
            "filename": path.name,
            "size_bytes": path.stat().st_size,
            "sha256": _sha256(path),
            "profiled_at_utc": datetime.now(timezone.utc).isoformat(),
            "year": year,
            "month": month,
        },
        "parquet": {
            "row_count": row_count,
            "row_groups": parquet.metadata.num_row_groups,
            "created_by": parquet.metadata.created_by,
        },
        "schema": {
            "fields": [
                (field.name, str(field.type), nulls[field.name])
                for field in parquet.schema_arrow
            ],
            "missing": [name for name in EXPECTED_COLUMNS if name not in names],
            "unexpected": [name for name in names if name not in expected],
        },
        "timestamps": {
            "pickup_min": pickup_min,
            "pickup_max": pickup_max,
            "dropoff_min": dropoff_min,
            "dropoff_max": dropoff_max,
        },
        "metrics": metrics,
        "quality": quality,
        "zone_lookup": {
            "sha256": _sha256(zone_lookup_path) if zone_lookup_path else None,
            "location_count": len(zone_ids) if zone_ids is not None else None,
        },
    }


def _update_metric(
    metric: dict[str, Any], values: list[Any], offset: int, stride: int
) -> None:
    for index, raw_value in enumerate(values):
        if raw_value is None:
            continue
        value = float(raw_value)
        metric["count"] += 1
        metric["min"] = value if metric["min"] is None else min(metric["min"], value)
        metric["max"] = value if metric["max"] is None else max(metric["max"], value)
        if (offset + index) % stride == 0:
            metric["sample"].append(value)


def _finish_metric(metric: dict[str, Any]) -> None:
    sample = sorted(metric.pop("sample"))
    metric["sample_count"] = len(sample)
    for name, quantile in (("p50", 0.50), ("p95", 0.95), ("p99", 0.99)):
        metric[name] = sample[round(quantile * (len(sample) - 1))] if sample else None


def _values(columns: dict[str, pa.Array], name: str, rows: int) -> list[Any]:
    return columns[name].to_pylist() if name in columns else [None] * rows


def _read_zone_ids(path: Path) -> set[int]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            if not reader.fieldnames or "LocationID" not in reader.fieldnames:
                raise SourceProfileError("Taxi Zone Lookup needs LocationID")
            return {int(row["LocationID"]) for row in reader if row["LocationID"]}
    except (OSError, ValueError, csv.Error) as error:
        raise SourceProfileError(f"Cannot read Taxi Zone Lookup: {error}") from error


def _count_zones(
    values: list[Any],
    zone_ids: set[int] | None,
    quality: dict[str, int],
    prefix: str,
) -> None:
    for value in values:
        if value is None:
            quality[f"{prefix}_zone_null"] += 1
        elif zone_ids is not None and int(value) not in zone_ids:
            quality[f"{prefix}_zone_unmapped"] += 1


def _count_true(values: pa.Array) -> int:
    count = pc.sum(pc.cast(pc.fill_null(values, False), pa.int64())).as_py()
    return int(count or 0)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source_file:
        for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True)
    parser.add_argument("--zone-lookup", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args(arguments)
    profile = profile_parquet(
        options.path,
        year=options.year,
        month=options.month,
        zone_lookup_path=options.zone_lookup,
    )
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(
        render_markdown(profile), encoding="utf-8", newline="\n"
    )
    print(
        f"Profiled {profile['parquet']['row_count']:,} rows; "
        f"report written to {options.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
