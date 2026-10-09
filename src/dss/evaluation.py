"""Forecast metrics that remain well-defined with zero-demand cells."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from dss.contracts import ContractError


def regression_metrics(actual: pd.Series, predicted: pd.Series) -> dict[str, float]:
    """Calculate MAE, RMSE, and WAPE; WAPE is NaN when total actual is zero."""

    y_true = _numeric(actual, "actual")
    y_pred = _numeric(predicted, "predicted")
    if len(y_true) != len(y_pred) or not len(y_true):
        raise ContractError("actual and predicted must have the same non-zero length")
    if (y_true < 0).any() or (y_pred < 0).any():
        raise ContractError("actual and predicted demand must be non-negative")
    error = y_true - y_pred
    absolute = np.abs(error)
    denominator = float(y_true.sum())
    return {
        "mae": float(absolute.mean()),
        "rmse": float(math.sqrt(np.square(error).mean())),
        "wape": float(absolute.sum() / denominator) if denominator else math.nan,
        "actual_total": denominator,
        "predicted_total": float(y_pred.sum()),
        "row_count": float(len(y_true)),
    }


def evaluate_predictions(
    frame: pd.DataFrame,
    *,
    prediction_column: str,
    group_by: tuple[str, ...] = (),
) -> pd.DataFrame:
    """Evaluate overall or by one or more operational dimensions."""

    required = {"trip_count", prediction_column, *group_by}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ContractError("evaluation frame is missing: " + ", ".join(missing))
    if not group_by:
        return pd.DataFrame(
            [regression_metrics(frame["trip_count"], frame[prediction_column])]
        )

    rows: list[dict[str, object]] = []
    grouper: str | list[str] = group_by[0] if len(group_by) == 1 else list(group_by)
    for keys, group in frame.groupby(grouper, dropna=False, observed=True):
        values = keys if isinstance(keys, tuple) else (keys,)
        dimensions = dict(zip(group_by, values, strict=True))
        rows.append(
            {
                **dimensions,
                **regression_metrics(group["trip_count"], group[prediction_column]),
            }
        )
    return pd.DataFrame(rows)


def _numeric(values: pd.Series, label: str) -> np.ndarray:
    try:
        result = pd.to_numeric(values, errors="raise").to_numpy(dtype="float64")
    except (TypeError, ValueError) as error:
        raise ContractError(f"{label} must be numeric") from error
    if not np.isfinite(result).all():
        raise ContractError(f"{label} must contain finite non-null values")
    return result
