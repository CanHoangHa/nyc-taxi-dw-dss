"""Deterministic chronological train/validation/test splitting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from dss.contracts import ContractError


@dataclass(frozen=True)
class TemporalSplit:
    train_start: date
    train_end: date
    validation_start: date
    validation_end: date
    test_start: date
    test_end: date

    def validate(self) -> None:
        boundaries = [
            pd.Timestamp(self.train_start),
            pd.Timestamp(self.train_end),
            pd.Timestamp(self.validation_start),
            pd.Timestamp(self.validation_end),
            pd.Timestamp(self.test_start),
            pd.Timestamp(self.test_end),
        ]
        if not (
            boundaries[0] <= boundaries[1]
            < boundaries[2]
            <= boundaries[3]
            < boundaries[4]
            <= boundaries[5]
        ):
            raise ContractError(
                "temporal split must be ordered and non-overlapping: train < validation < test"
            )


@dataclass(frozen=True)
class SplitFrames:
    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame


def split_by_date(frame: pd.DataFrame, boundaries: TemporalSplit) -> SplitFrames:
    """Split rows using inclusive date boundaries without shuffling."""

    boundaries.validate()
    if "demand_date" not in frame.columns:
        raise ContractError("feature frame is missing demand_date")
    result = frame.copy()
    result["demand_date"] = pd.to_datetime(result["demand_date"], errors="raise").dt.normalize()

    def select(start: date, end: date) -> pd.DataFrame:
        mask = result["demand_date"].between(pd.Timestamp(start), pd.Timestamp(end))
        return result.loc[mask].sort_values(
            ["demand_date", "demand_hour", "pickup_zone_key"], ignore_index=True
        )

    parts = SplitFrames(
        train=select(boundaries.train_start, boundaries.train_end),
        validation=select(boundaries.validation_start, boundaries.validation_end),
        test=select(boundaries.test_start, boundaries.test_end),
    )
    if any(part.empty for part in (parts.train, parts.validation, parts.test)):
        raise ContractError("each temporal split must contain at least one row")
    return parts
