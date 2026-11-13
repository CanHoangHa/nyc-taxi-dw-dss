"""Leakage-safe calendar, lag, and rolling demand features."""

from __future__ import annotations

from datetime import timedelta

import pandas as pd

from dss.contracts import ContractError, DEMAND_GRAIN


GROUP_KEYS = ["pickup_location_id", "demand_hour"]
MODEL_FEATURES = (
    "pickup_location_id",
    "demand_hour",
    "day_of_week",
    "month",
    "day_of_month",
    "is_weekend",
    "lag_1d",
    "lag_2d",
    "lag_7d",
    "rolling_mean_7d",
    "rolling_median_28d",
    "rolling_std_7d",
    "same_weekday_median_4w",
)
HISTORY_FEATURES = (
    "lag_1d",
    "lag_2d",
    "lag_7d",
    "rolling_mean_7d",
    "rolling_median_28d",
    "rolling_std_7d",
    "same_weekday_median_4w",
)


def build_features(dense_demand: pd.DataFrame) -> pd.DataFrame:
    """Build features available before the forecast date starts.

    Missing history is represented as NaN and exposed by
    ``is_feature_complete``. Callers decide whether to drop warm-up rows.
    """

    required = {
        *DEMAND_GRAIN,
        "pickup_location_id",
        "borough",
        "zone_name",
        "trip_count",
    }
    missing = sorted(required - set(dense_demand.columns))
    if missing:
        raise ContractError(
            "dense demand is missing required columns: " + ", ".join(missing)
        )

    result = dense_demand.copy()
    result["demand_date"] = pd.to_datetime(result["demand_date"], errors="raise").dt.normalize()
    if result["demand_date"].isna().any():
        raise ContractError("demand_date must not contain null values")
    if result.duplicated(list(DEMAND_GRAIN)).any():
        raise ContractError("dense demand grain must be unique")
    if (result["trip_count"] < 0).any():
        raise ContractError("trip_count must be non-negative")

    result = result.sort_values([*GROUP_KEYS, "demand_date"], ignore_index=True)
    dates = result["demand_date"]
    result["day_of_week"] = dates.dt.dayofweek.astype("int8")
    result["month"] = dates.dt.month.astype("int8")
    result["day_of_month"] = dates.dt.day.astype("int8")
    result["is_weekend"] = result["day_of_week"].ge(5)

    grouped = result.groupby(GROUP_KEYS, sort=False, observed=True)
    for days in (1, 2, 7):
        previous_date = grouped["demand_date"].shift(days)
        previous_target = grouped["trip_count"].shift(days).astype("float64")
        exact = previous_date.eq(result["demand_date"] - timedelta(days=days))
        result[f"lag_{days}d"] = previous_target.where(exact)

    shifted_target = grouped["trip_count"].shift(1).astype("float64")
    shifted_date = grouped["demand_date"].shift(1)
    for window, statistic, output in (
        (7, "mean", "rolling_mean_7d"),
        (7, "std", "rolling_std_7d"),
        (28, "median", "rolling_median_28d"),
    ):
        rolling = shifted_target.groupby(
            [result[key] for key in GROUP_KEYS], sort=False, observed=True
        ).rolling(window, min_periods=window)
        values = getattr(rolling, statistic)().reset_index(level=GROUP_KEYS, drop=True)
        oldest_date = grouped["demand_date"].shift(window)
        contiguous = shifted_date.eq(result["demand_date"] - timedelta(days=1))
        contiguous &= oldest_date.eq(
            result["demand_date"] - timedelta(days=window)
        )
        result[output] = values.where(contiguous)

    weekday_group = result.groupby(
        [*GROUP_KEYS, "day_of_week"], sort=False, observed=True
    )
    weekday_shifted = weekday_group["trip_count"].shift(1).astype("float64")
    weekday_dates = weekday_group["demand_date"].shift(1)
    weekday_oldest = weekday_group["demand_date"].shift(4)
    weekday_values = weekday_shifted.groupby(
        [result[key] for key in [*GROUP_KEYS, "day_of_week"]],
        sort=False,
        observed=True,
    ).rolling(4, min_periods=4).median().reset_index(
        level=[*GROUP_KEYS, "day_of_week"], drop=True
    )
    exact_weekdays = weekday_dates.eq(result["demand_date"] - timedelta(days=7))
    exact_weekdays &= weekday_oldest.eq(
        result["demand_date"] - timedelta(days=28)
    )
    result["same_weekday_median_4w"] = weekday_values.where(exact_weekdays)

    result["is_feature_complete"] = result[list(HISTORY_FEATURES)].notna().all(axis=1)
    for column in HISTORY_FEATURES:
        result[column] = result[column].astype("float32")
    return result.sort_values(list(DEMAND_GRAIN), ignore_index=True)


def complete_feature_rows(features: pd.DataFrame) -> pd.DataFrame:
    """Return rows with the full 28-day pre-forecast history contract."""

    if "is_feature_complete" not in features.columns:
        raise ContractError("feature frame is missing is_feature_complete")
    return features.loc[features["is_feature_complete"]].reset_index(drop=True)
