"""Markdown rendering for the TLC source profile."""

from __future__ import annotations

from typing import Any


def render_markdown(profile: dict[str, Any]) -> str:
    """Render a reviewable Markdown summary."""

    source = profile["source"]
    parquet = profile["parquet"]
    schema = profile["schema"]
    timestamps = profile["timestamps"]
    total = parquet["row_count"]
    lines = [
        f"# Yellow Taxi {source['year']}-{source['month']:02d} Source Profile",
        "",
        "## Source",
        "",
        f"- URL: {source['url']}",
        f"- File: {source['filename']}",
        f"- Size: {source['size_bytes']:,} bytes",
        f"- SHA-256: {source['sha256']}",
        f"- Profiled at (UTC): {source['profiled_at_utc']}",
        f"- Rows: {total:,}",
        f"- Row groups: {parquet['row_groups']}",
        f"- Created by: {parquet['created_by']}",
        f"- Zone lookup SHA-256: {profile['zone_lookup']['sha256'] or 'not supplied'}",
        f"- Zone IDs: {profile['zone_lookup']['location_count'] or 'not supplied'}",
        "",
        "The Parquet file stays under Git-ignored data/raw.",
        "",
        "## Schema",
        "",
        "| # | Field | Arrow type | Nulls | Proposed RAW type |",
        "|---:|---|---|---:|---|",
    ]
    for index, (name, arrow_type, nulls) in enumerate(schema["fields"], start=1):
        lines.append(
            f"| {index} | {name} | {arrow_type} | {nulls:,} | "
            f"{_postgres_type(arrow_type)} |"
        )
    lines += [
        "",
        f"- Missing fields: {', '.join(schema['missing']) or 'none'}",
        f"- Unexpected fields: {', '.join(schema['unexpected']) or 'none'}",
        "",
        "## Timestamp coverage",
        "",
        f"- Pickup: {timestamps['pickup_min']} to {timestamps['pickup_max']}",
        f"- Drop-off: {timestamps['dropoff_min']} to {timestamps['dropoff_max']}",
        "",
        "## Numeric profile",
        "",
        "Quantiles use a deterministic bounded sample; counts and bounds are exact.",
        "",
        "| Metric | Count | Min | Sample p50 | Sample p95 | Sample p99 | Max |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, metric in profile["metrics"].items():
        lines.append(
            f"| {name} | {metric['count']:,} | {_number(metric['min'])} | "
            f"{_number(metric['p50'])} | {_number(metric['p95'])} | "
            f"{_number(metric['p99'])} | {_number(metric['max'])} |"
        )
    lines += [
        "",
        "## Initial quality indicators",
        "",
        "| Indicator | Rows |",
        "|---|---:|",
    ]
    for name, count in profile["quality"].items():
        percentage = count / total * 100 if total else 0
        lines.append(f"| {name} | {count:,} ({percentage:.4f}%) |")
    lines += [
        "",
        "This source profile does not apply upper data-quality thresholds; approved "
        "thresholds are documented in docs/design_decisions.md.",
        "Negative monetary rows remain traceable and are not silently removed.",
        "",
        "## Reproduce",
        "",
        "~~~powershell",
        "$env:PYTHONPATH = (Resolve-Path \"src\").Path",
        ".\\.venv\\Scripts\\python.exe -m taxi_dw.source_profile "
        "--path data/raw/yellow/2024/01/yellow_tripdata_2024-01.parquet "
        "--year 2024 --month 1 "
        "--zone-lookup src/dbt/seeds/taxi_zone_lookup.csv "
        "--output docs/profiles/yellow_tripdata_2024_01.md",
        "~~~",
        "",
    ]
    return "\n".join(lines)


def _postgres_type(arrow_type: str) -> str:
    if arrow_type.startswith("timestamp"):
        return "timestamp without time zone"
    if arrow_type in {"int8", "int16", "int32"}:
        return "integer"
    if arrow_type.startswith(("int", "uint")):
        return "bigint"
    if arrow_type in {"float", "double", "halffloat"}:
        return "double precision"
    if arrow_type in {"string", "large_string"}:
        return "text"
    return "review required"


def _number(value: float | None) -> str:
    return "n/a" if value is None else f"{value:,.4f}"
