"""Transactional Gate C persistence and read repository."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
import json
from typing import Any
from uuid import UUID, uuid4

import numpy as np
import pandas as pd
import psycopg
from psycopg.rows import dict_row

from dss.contracts import ContractError
from taxi_dw.db import open_connection


FORECAST_COLUMNS = (
    "forecast_date",
    "demand_hour",
    "pickup_zone_key",
    "pickup_location_id",
    "borough",
    "zone_name",
    "predicted_trip_count",
    "baseline_trip_count",
    "historical_p50",
    "historical_p75",
    "demand_ratio",
    "demand_level",
    "recommendation",
    "recommendation_reason",
    "is_actionable",
)


@dataclass(frozen=True)
class ModelRunMetadata:
    model_name: str
    model_version: str
    feature_version: str
    recommendation_version: str
    train_start_date: date
    train_end_date: date
    validation_start_date: date
    validation_end_date: date
    metrics: Mapping[str, Any]
    git_commit_sha: str


class ForecastRepository:
    """Write a complete run atomically and expose dashboard-oriented reads."""

    def __init__(self, connection: psycopg.Connection | None = None):
        self._shared_connection = connection

    @contextmanager
    def _connection(self) -> Iterator[psycopg.Connection]:
        if self._shared_connection is not None:
            yield self._shared_connection
        else:
            with open_connection() as connection:
                yield connection

    def save_run(
        self,
        metadata: ModelRunMetadata,
        forecasts: pd.DataFrame,
        *,
        run_id: UUID | None = None,
    ) -> UUID:
        """Insert metadata and all forecast rows in one database transaction."""

        _validate_metadata(metadata)
        normalized = validate_forecasts(forecasts)
        identifier = run_id or uuid4()
        with self._connection() as connection:
            with connection.transaction():
                with connection.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO dss.model_run ("
                        "run_id, model_name, model_version, feature_version, "
                        "recommendation_version, train_start_date, train_end_date, "
                        "validation_start_date, validation_end_date, metrics_json, "
                        "git_commit_sha) VALUES ("
                        "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)",
                        (
                            identifier,
                            metadata.model_name,
                            metadata.model_version,
                            metadata.feature_version,
                            metadata.recommendation_version,
                            metadata.train_start_date,
                            metadata.train_end_date,
                            metadata.validation_start_date,
                            metadata.validation_end_date,
                            json.dumps(metadata.metrics, allow_nan=False),
                            metadata.git_commit_sha,
                        ),
                    )
                    cursor.executemany(
                        "INSERT INTO dss.zone_hour_forecast ("
                        "run_id, forecast_date, demand_hour, pickup_zone_key, "
                        "pickup_location_id, borough, zone_name, "
                        "predicted_trip_count, baseline_trip_count, historical_p50, "
                        "historical_p75, demand_ratio, demand_level, recommendation, "
                        "recommendation_reason, is_actionable) VALUES ("
                        "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        [
                            (identifier, *row)
                            for row in normalized.loc[:, FORECAST_COLUMNS].itertuples(
                                index=False, name=None
                            )
                        ],
                    )
        return identifier

    def available_forecast_dates(self) -> list[date]:
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT DISTINCT forecast_date "
                    "FROM dss.zone_hour_forecast ORDER BY forecast_date DESC"
                )
                return [row[0] for row in cursor.fetchall()]

    def latest_run(self, forecast_date: date | None = None) -> dict[str, Any] | None:
        parameters: tuple[date, ...] = ()
        condition = ""
        if forecast_date is not None:
            condition = (
                "WHERE EXISTS (SELECT 1 FROM dss.zone_hour_forecast f "
                "WHERE f.run_id = r.run_id AND f.forecast_date = %s) "
            )
            parameters = (forecast_date,)
        with self._connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    "SELECT r.* FROM dss.model_run r "
                    + condition
                    + "ORDER BY r.created_at DESC, r.run_id DESC LIMIT 1",
                    parameters,
                )
                row = cursor.fetchone()
                return dict(row) if row is not None else None

    def read_forecasts(
        self,
        run_id: UUID,
        *,
        forecast_date: date | None = None,
    ) -> pd.DataFrame:
        parameters: list[Any] = [run_id]
        condition = ""
        if forecast_date is not None:
            condition = " AND forecast_date = %s"
            parameters.append(forecast_date)
        with self._connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    "SELECT * FROM dss.zone_hour_forecast "
                    "WHERE run_id = %s"
                    + condition
                    + " ORDER BY forecast_date, demand_hour, pickup_location_id",
                    tuple(parameters),
                )
                rows = cursor.fetchall()
        return pd.DataFrame(rows)


def validate_forecasts(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate the complete, rectangular Gate C forecast contract."""

    missing = [column for column in FORECAST_COLUMNS if column not in frame.columns]
    if missing:
        raise ContractError("forecast output is missing: " + ", ".join(missing))
    if frame.empty:
        raise ContractError("forecast output must not be empty")
    result = frame.loc[:, FORECAST_COLUMNS].copy()
    result["forecast_date"] = pd.to_datetime(
        result["forecast_date"], errors="raise"
    ).dt.date
    if result["forecast_date"].isna().any():
        raise ContractError("forecast_date must not contain null values")
    non_null = [column for column in FORECAST_COLUMNS if column != "forecast_date"]
    if result[non_null].isna().any().any():
        raise ContractError("forecast output must not contain null values")
    grain = ["forecast_date", "demand_hour", "pickup_zone_key"]
    if result.duplicated(grain).any():
        raise ContractError("forecast output grain must be unique")
    hours = pd.to_numeric(result["demand_hour"], errors="raise")
    locations = pd.to_numeric(result["pickup_location_id"], errors="raise")
    if not np.equal(hours, np.floor(hours)).all() or not hours.between(0, 23).all():
        raise ContractError("forecast demand_hour must be within 0..23")
    if not np.equal(locations, np.floor(locations)).all() or not locations.gt(0).all():
        raise ContractError("forecast pickup_location_id must be a positive integer")
    result["demand_hour"] = hours.astype("int8")
    result["pickup_location_id"] = locations.astype("int16")
    numeric = [
        "predicted_trip_count",
        "baseline_trip_count",
        "historical_p50",
        "historical_p75",
        "demand_ratio",
    ]
    values = result[numeric].apply(pd.to_numeric, errors="raise")
    if not np.isfinite(values.to_numpy(dtype="float64")).all() or (values < 0).any().any():
        raise ContractError("forecast measures must be finite and non-negative")
    if (result["historical_p75"] < result["historical_p50"]).any():
        raise ContractError("historical_p75 must not be below historical_p50")
    if not result["demand_level"].isin(
        ["Low", "Medium", "High", "Not applicable"]
    ).all():
        raise ContractError("forecast contains an invalid demand level")
    text_columns = [
        "pickup_zone_key",
        "borough",
        "zone_name",
        "recommendation",
        "recommendation_reason",
    ]
    if any(result[column].astype(str).str.strip().eq("").any() for column in text_columns):
        raise ContractError("forecast text fields must be non-blank")
    expected_actionable = result["pickup_location_id"].between(1, 263)
    if not result["is_actionable"].map(
        lambda value: isinstance(value, (bool, np.bool_))
    ).all() or not result["is_actionable"].eq(expected_actionable).all():
        raise ContractError("is_actionable must match TLC LocationID 1-263")

    for forecast_date, daily in result.groupby("forecast_date", sort=False):
        zones = daily["pickup_zone_key"].nunique()
        if len(daily) != zones * 24:
            raise ContractError(
                f"forecast date {forecast_date} must contain 24 rows per zone"
            )
        hours_per_zone = daily.groupby("pickup_zone_key")["demand_hour"].nunique()
        if not hours_per_zone.eq(24).all():
            raise ContractError(
                f"forecast date {forecast_date} must contain every hour per zone"
            )
    return result.sort_values(grain, ignore_index=True)


def _validate_metadata(metadata: ModelRunMetadata) -> None:
    text_fields = (
        metadata.model_name,
        metadata.model_version,
        metadata.feature_version,
        metadata.recommendation_version,
        metadata.git_commit_sha,
    )
    if any(not value.strip() for value in text_fields):
        raise ContractError("model-run text metadata must be non-blank")
    if not (
        metadata.train_start_date
        <= metadata.train_end_date
        < metadata.validation_start_date
        <= metadata.validation_end_date
    ):
        raise ContractError("model-run train and validation dates must be ordered")
    try:
        json.dumps(metadata.metrics, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ContractError("model-run metrics must be finite JSON data") from error
