"""Transparent demand-forecasting baselines."""

from __future__ import annotations

import pandas as pd

from dss.contracts import ContractError


BASELINE_COLUMNS = {
    "seasonal_naive": "lag_7d",
    "same_weekday_median": "same_weekday_median_4w",
}


def predict_baseline(features: pd.DataFrame, name: str) -> pd.Series:
    """Return non-negative predictions for one declared baseline."""

    if name not in BASELINE_COLUMNS:
        raise ContractError(f"unknown baseline: {name}")
    source = BASELINE_COLUMNS[name]
    if source not in features.columns:
        raise ContractError(f"feature frame is missing {source}")
    if features[source].isna().any():
        raise ContractError(f"baseline {name} has incomplete history")
    if (features[source] < 0).any():
        raise ContractError(f"baseline {name} produced a negative prediction")
    return features[source].astype("float64").rename("predicted_trip_count")


def add_baseline_predictions(features: pd.DataFrame) -> pd.DataFrame:
    """Attach both required baseline predictions to complete feature rows."""

    result = features.copy()
    for name in BASELINE_COLUMNS:
        result[f"prediction_{name}"] = predict_baseline(result, name)
    return result
