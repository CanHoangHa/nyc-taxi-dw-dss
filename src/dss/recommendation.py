"""Deterministic, explainable demand-level recommendations."""

from __future__ import annotations

import numpy as np
import pandas as pd

from dss.contracts import ContractError


RECOMMENDATION_VERSION = "1.1.0"
RECOMMENDATION_TEXT = {
    "Low": "Không cần ưu tiên bổ sung; duy trì mức sẵn sàng thông thường.",
    "Medium": "Theo dõi và duy trì khả năng sẵn sàng tại zone-hour này.",
    "High": "Ưu tiên tăng khả năng sẵn sàng của taxi tại zone-hour này.",
    "Not applicable": "Không phát khuyến nghị điều phối cho zone ngoài phạm vi vận hành.",
}


def fit_demand_thresholds(training: pd.DataFrame) -> pd.DataFrame:
    """Learn p50/p75 per stable zone-hour using training history only."""

    required = {"pickup_location_id", "demand_hour", "trip_count"}
    missing = sorted(required - set(training.columns))
    if missing:
        raise ContractError("threshold training frame is missing: " + ", ".join(missing))
    if training.empty or training["trip_count"].isna().any():
        raise ContractError("threshold training history must be complete and non-empty")
    if (training["trip_count"] < 0).any():
        raise ContractError("threshold training target must be non-negative")
    thresholds = (
        training.groupby(["pickup_location_id", "demand_hour"], observed=True)[
            "trip_count"
        ]
        .quantile([0.5, 0.75])
        .unstack()
        .rename(columns={0.5: "historical_p50", 0.75: "historical_p75"})
        .reset_index()
    )
    return thresholds


def add_recommendations(
    forecasts: pd.DataFrame,
    thresholds: pd.DataFrame,
    *,
    prediction_column: str = "predicted_trip_count",
    baseline_column: str = "baseline_trip_count",
) -> pd.DataFrame:
    """Attach ratio, level, localized recommendation, and rule explanation."""

    required = {
        "pickup_location_id",
        "demand_hour",
        "is_actionable",
        prediction_column,
        baseline_column,
    }
    missing = sorted(required - set(forecasts.columns))
    if missing:
        raise ContractError("forecast frame is missing: " + ", ".join(missing))
    threshold_columns = {
        "pickup_location_id",
        "demand_hour",
        "historical_p50",
        "historical_p75",
    }
    missing_thresholds = sorted(threshold_columns - set(thresholds.columns))
    if missing_thresholds:
        raise ContractError(
            "threshold frame is missing: " + ", ".join(missing_thresholds)
        )
    if thresholds.duplicated(["pickup_location_id", "demand_hour"]).any():
        raise ContractError("threshold grain must be unique per zone-hour")

    result = forecasts.merge(
        thresholds.loc[:, sorted(threshold_columns)],
        on=["pickup_location_id", "demand_hour"],
        how="left",
        validate="many_to_one",
    )
    numeric_columns = [
        prediction_column,
        baseline_column,
        "historical_p50",
        "historical_p75",
    ]
    if result[numeric_columns].isna().any().any():
        raise ContractError("forecast rows must have prediction, baseline, and thresholds")
    if (result[numeric_columns] < 0).any().any():
        raise ContractError("prediction, baseline, and thresholds must be non-negative")
    actionable = result["is_actionable"].map(
        lambda value: isinstance(value, (bool, np.bool_))
    )
    if not actionable.all():
        raise ContractError("is_actionable must contain boolean values")

    result["demand_ratio"] = result[prediction_column] / result[
        baseline_column
    ].clip(lower=1)
    high = (
        result[prediction_column].ge(result["historical_p75"])
        & result["demand_ratio"].ge(1.15)
    )
    medium = result[prediction_column].ge(result["historical_p50"]) | result[
        "demand_ratio"
    ].ge(1.0)
    result["demand_level"] = np.select(
        [~result["is_actionable"], high, medium],
        ["Not applicable", "High", "Medium"],
        default="Low",
    )
    result["recommendation"] = result["demand_level"].map(RECOMMENDATION_TEXT)
    result["recommendation_reason"] = np.select(
        [
            ~result["is_actionable"],
            high,
            medium,
        ],
        [
            "Zone nằm ngoài phạm vi điều phối 1-263.",
            "Prediction đạt p75 lịch sử và cao hơn baseline ít nhất 15%.",
            "Prediction đạt p50 lịch sử hoặc không thấp hơn baseline.",
        ],
        default="Prediction dưới p50 lịch sử và thấp hơn baseline.",
    )
    result["recommendation_version"] = RECOMMENDATION_VERSION
    return result
