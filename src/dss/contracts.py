"""Data contracts at the warehouse-to-DSS boundary."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd


DEMAND_GRAIN = ("demand_date", "demand_hour", "pickup_zone_key")
SPARSE_DEMAND_COLUMNS = (
    "demand_date",
    "demand_hour",
    "pickup_zone_key",
    "pickup_location_id",
    "borough",
    "zone_name",
    "is_recommendation_eligible",
    "trip_count",
)
COVERAGE_COLUMNS = (
    "source_year",
    "source_month",
    "coverage_start_date",
    "coverage_end_date",
    "valid_trip_count",
)
ZONE_COLUMNS = (
    "pickup_zone_key",
    "pickup_location_id",
    "borough",
    "zone_name",
    "is_recommendation_eligible",
)


class ContractError(ValueError):
    """Raised when a published warehouse interface violates the DSS contract."""


def validate_sparse_demand(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a normalized copy of the sparse positive-demand mart rows."""

    _require_columns(frame, SPARSE_DEMAND_COLUMNS, "demand mart")
    result = frame.loc[:, SPARSE_DEMAND_COLUMNS].copy()
    result["demand_date"] = _dates(result["demand_date"], "demand_date")
    result["demand_hour"] = _integers(
        result["demand_hour"], "demand_hour", minimum=0, maximum=23
    ).astype("int8")
    result["pickup_location_id"] = _integers(
        result["pickup_location_id"], "pickup_location_id", minimum=1
    ).astype("int16")
    result["trip_count"] = _integers(
        result["trip_count"], "trip_count", minimum=1
    ).astype("int64")
    result["is_recommendation_eligible"] = _booleans(
        result["is_recommendation_eligible"], "is_recommendation_eligible"
    )
    _require_nonblank_text(result, ("pickup_zone_key", "borough", "zone_name"))
    _require_unique(result, DEMAND_GRAIN, "demand mart grain")
    _validate_zone_mapping(result)

    expected_eligibility = result["pickup_location_id"].between(1, 263)
    mismatch = result["is_recommendation_eligible"] != expected_eligibility
    if mismatch.any():
        raise ContractError(
            "is_recommendation_eligible must be true only for TLC zones 1-263"
        )
    return result.sort_values(list(DEMAND_GRAIN), ignore_index=True)


def validate_coverage(frame: pd.DataFrame) -> pd.DataFrame:
    """Return normalized reconciled months whose missing cells may be zero-filled."""

    _require_columns(frame, COVERAGE_COLUMNS, "demand coverage")
    result = frame.loc[:, COVERAGE_COLUMNS].copy()
    result["source_year"] = _integers(
        result["source_year"], "source_year", minimum=2000, maximum=2100
    ).astype("int16")
    result["source_month"] = _integers(
        result["source_month"], "source_month", minimum=1, maximum=12
    ).astype("int8")
    result["valid_trip_count"] = _integers(
        result["valid_trip_count"], "valid_trip_count", minimum=0
    ).astype("int64")
    result["coverage_start_date"] = _dates(
        result["coverage_start_date"], "coverage_start_date"
    )
    result["coverage_end_date"] = _dates(
        result["coverage_end_date"], "coverage_end_date"
    )
    _require_unique(result, ("source_year", "source_month"), "coverage month")

    expected_start = pd.to_datetime(
        {
            "year": result["source_year"],
            "month": result["source_month"],
            "day": np.ones(len(result), dtype="int8"),
        }
    )
    expected_end = expected_start + pd.offsets.MonthEnd(0)
    if not result["coverage_start_date"].equals(expected_start):
        raise ContractError("coverage_start_date must be the first day of its month")
    if not result["coverage_end_date"].equals(expected_end):
        raise ContractError("coverage_end_date must be the last day of its month")
    return result.sort_values(
        ["coverage_start_date"], ignore_index=True
    )


def validate_zones(frame: pd.DataFrame) -> pd.DataFrame:
    """Return normalized recommendation-eligible taxi-zone members."""

    _require_columns(frame, ZONE_COLUMNS, "eligible zones")
    result = frame.loc[:, ZONE_COLUMNS].copy()
    result["pickup_location_id"] = _integers(
        result["pickup_location_id"], "pickup_location_id", minimum=1, maximum=263
    ).astype("int16")
    result["is_recommendation_eligible"] = _booleans(
        result["is_recommendation_eligible"], "is_recommendation_eligible"
    )
    if not result["is_recommendation_eligible"].all():
        raise ContractError("eligible-zone input may contain only zones 1-263")
    _require_nonblank_text(result, ("pickup_zone_key", "borough", "zone_name"))
    _require_unique(result, ("pickup_zone_key",), "zone key")
    _require_unique(result, ("pickup_location_id",), "zone business identifier")
    _validate_zone_mapping(result)
    return result.sort_values(["pickup_location_id"], ignore_index=True)


def covered_dates(coverage: pd.DataFrame) -> pd.DatetimeIndex:
    """Expand validated coverage rows into their exact covered calendar dates."""

    normalized = validate_coverage(coverage)
    ranges = [
        pd.date_range(row.coverage_start_date, row.coverage_end_date, freq="D")
        for row in normalized.itertuples(index=False)
    ]
    if not ranges:
        return pd.DatetimeIndex([], dtype="datetime64[ns]")
    dates = ranges[0]
    for additional in ranges[1:]:
        dates = dates.append(additional)
    return pd.DatetimeIndex(dates.unique()).sort_values()


def require_covered_range(
    coverage: pd.DataFrame, start_date: date, end_date: date
) -> pd.DatetimeIndex:
    """Return covered dates in a requested range or fail on any uncovered day."""

    start = pd.Timestamp(start_date).normalize()
    end = pd.Timestamp(end_date).normalize()
    if start > end:
        raise ContractError("start_date must not be after end_date")
    expected = pd.date_range(start, end, freq="D")
    available = covered_dates(coverage)
    missing = expected.difference(available)
    if not missing.empty:
        labels = ", ".join(value.strftime("%Y-%m-%d") for value in missing[:3])
        suffix = "..." if len(missing) > 3 else ""
        raise ContractError(f"requested range contains uncovered dates: {labels}{suffix}")
    return expected


def _require_columns(
    frame: pd.DataFrame, required: tuple[str, ...], interface_name: str
) -> None:
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ContractError(
            f"{interface_name} is missing required columns: {', '.join(missing)}"
        )


def _dates(values: pd.Series, name: str) -> pd.Series:
    try:
        parsed = pd.to_datetime(values, errors="raise")
    except (TypeError, ValueError) as error:
        raise ContractError(f"{name} contains invalid dates") from error
    if parsed.isna().any():
        raise ContractError(f"{name} must not contain null values")
    if getattr(parsed.dt, "tz", None) is not None:
        parsed = parsed.dt.tz_localize(None)
    return parsed.dt.normalize()


def _integers(
    values: pd.Series,
    name: str,
    *,
    minimum: int,
    maximum: int | None = None,
) -> pd.Series:
    try:
        numeric = pd.to_numeric(values, errors="raise")
    except (TypeError, ValueError) as error:
        raise ContractError(f"{name} must contain integer values") from error
    if numeric.isna().any() or not np.isfinite(numeric.astype("float64")).all():
        raise ContractError(f"{name} must contain finite non-null values")
    if not np.equal(numeric, np.floor(numeric)).all():
        raise ContractError(f"{name} must contain integer values")
    if (numeric < minimum).any() or (
        maximum is not None and (numeric > maximum).any()
    ):
        bounds = f"{minimum}..{maximum}" if maximum is not None else f">={minimum}"
        raise ContractError(f"{name} must be within {bounds}")
    return numeric


def _booleans(values: pd.Series, name: str) -> pd.Series:
    if values.isna().any():
        raise ContractError(f"{name} must not contain null values")
    if not values.map(lambda value: isinstance(value, (bool, np.bool_))).all():
        raise ContractError(f"{name} must contain boolean values")
    return values.astype(bool)


def _require_nonblank_text(frame: pd.DataFrame, columns: tuple[str, ...]) -> None:
    for column in columns:
        values = frame[column]
        if values.isna().any() or values.astype(str).str.strip().eq("").any():
            raise ContractError(f"{column} must contain non-blank text")


def _require_unique(
    frame: pd.DataFrame, columns: tuple[str, ...], label: str
) -> None:
    if frame.duplicated(list(columns)).any():
        raise ContractError(f"{label} must be unique on {', '.join(columns)}")


def _validate_zone_mapping(frame: pd.DataFrame) -> None:
    mappings = (
        "pickup_zone_key",
        "pickup_location_id",
        "borough",
        "zone_name",
        "is_recommendation_eligible",
    )
    for key in ("pickup_zone_key", "pickup_location_id"):
        other = [column for column in mappings if column != key]
        if (frame.groupby(key, dropna=False)[other].nunique(dropna=False) > 1).any().any():
            raise ContractError(f"zone metadata is inconsistent for {key}")
