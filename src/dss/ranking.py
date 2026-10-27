"""Pickup concentration ranking, independent of hourly recommendation policy.

Intervals are half-open [start_hour, end_hour). Ranks use competition ranking;
Top K cuts ties by ascending zone ID for both methods, with exactly K zones.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from dss.contracts import ContractError

RANKING_VERSION = "1.1.0"


def rank_zone_interval(
    rows: pd.DataFrame, *, borough: str, start_hour: int, end_hour: int,
    zone_ids: tuple[int, ...] = (),
    zone_reference: pd.DataFrame,
) -> pd.DataFrame:
    if not borough or not isinstance(start_hour, int) or not isinstance(end_hour, int) or not 0 <= start_hour < end_hour <= 24:
        raise ContractError("ranking requires one borough and an interval within 0..24")
    required = {"forecast_date", "pickup_location_id", "zone_name", "borough", "demand_hour",
                "is_actionable", "predicted_trip_count", "baseline_trip_count"}
    if rows.empty:
        rows = pd.DataFrame(columns=sorted(required))
    if required - set(rows):
        raise ContractError("ranking forecast columns are incomplete")
    if not rows.empty and (rows.forecast_date.nunique(dropna=False) != 1 or rows.forecast_date.isna().any()):
        raise ContractError("ranking requires exactly one forecast date")
    # Resolve the universe before examining forecast coverage. Production callers
    # supply the complete dimension in one query, including absent forecast zones.
    reference = zone_reference.copy()
    reference_columns = {"pickup_location_id", "borough", "is_actionable"}
    if reference_columns - set(reference) or reference[list(reference_columns)].isna().any().any():
        raise ContractError("zone reference must contain complete zone, borough and eligibility")
    if reference.pickup_location_id.duplicated().any():
        raise ContractError("zone reference must have unique zone IDs")
    if not reference.is_actionable.map(lambda value: isinstance(value, (bool, np.bool_))).all():
        raise ContractError("zone reference eligibility must be boolean")
    if zone_ids:
        unknown = sorted(set(zone_ids) - set(reference.pickup_location_id))
        if unknown:
            raise ContractError(f"unknown requested zone IDs: {unknown}")
        requested = reference.loc[reference.pickup_location_id.isin(zone_ids)]
        outside = requested.loc[~requested.borough.eq(borough), "pickup_location_id"].tolist()
        ineligible = requested.loc[~requested.is_actionable | ~requested.pickup_location_id.between(1, 263), "pickup_location_id"].tolist()
        if outside:
            raise ContractError(f"requested zones outside borough {borough}: {outside}")
        if ineligible:
            raise ContractError(f"requested zones not operationally eligible: {ineligible}")
    candidates = reference.loc[reference.borough.eq(borough) & reference.is_actionable
                               & reference.pickup_location_id.between(1, 263)]
    if zone_ids:
        candidates = candidates.loc[candidates.pickup_location_id.isin(zone_ids)]
    candidate_ids = candidates.pickup_location_id
    candidate_rows = rows.loc[rows.pickup_location_id.isin(candidate_ids)]
    missing_zones = sorted(set(candidate_ids) - set(candidate_rows.pickup_location_id))
    if missing_zones:
        raise ContractError(f"missing forecast data for eligible zones: {missing_zones}")
    if not candidate_rows.borough.eq(borough).all() or not candidate_rows.is_actionable.map(
        lambda value: isinstance(value, (bool, np.bool_)) and bool(value)
    ).all():
        raise ContractError("forecast borough/eligibility disagrees with zone reference")
    selected = candidate_rows.loc[candidate_rows.demand_hour.ge(start_hour) & candidate_rows.demand_hour.lt(end_hour)].copy()
    counts = selected.groupby("pickup_location_id").demand_hour.nunique()
    if (selected.duplicated(["pickup_location_id", "demand_hour"]).any()
            or not counts.reindex(candidate_ids, fill_value=0).eq(end_hour-start_hour).all()
            or not selected.demand_hour.isin(range(start_hour, end_hour)).all()):
        raise ContractError("ranking requires every selected hour exactly once per candidate zone")
    if selected.empty:
        return pd.DataFrame()
    measures = selected[["predicted_trip_count", "baseline_trip_count"]].astype(float)
    if not np.isfinite(measures.to_numpy()).all() or (measures < 0).any().any():
        raise ContractError("ranking measures must be finite and non-negative")
    selected[measures.columns] = measures
    result = selected.groupby("pickup_location_id", as_index=False).agg(
        forecast_date=("forecast_date", "first"), borough=("borough", "first"),
        zone_name=("zone_name", "first"), predicted_trip_count=("predicted_trip_count", "sum"),
        baseline_trip_count=("baseline_trip_count", "sum"), hour_count=("demand_hour", "size"),
    )
    result["rank"] = result.predicted_trip_count.rank(method="min", ascending=False).astype(int)
    result["start_hour"], result["end_hour"] = start_hour, end_hour
    result["ranking_version"] = RANKING_VERSION
    result["ranking_reason"] = np.where(
        result.predicted_trip_count.eq(0),
        "Tổng dự báo bằng 0; không khuyến nghị bổ sung taxi.",
        "Hạng theo tổng pickup dự báo giảm dần; đồng tổng cùng hạng. Zone ID chỉ ổn định hiển thị.",
    )
    return result.sort_values(["predicted_trip_count", "pickup_location_id"], ascending=[False, True], ignore_index=True)


def evaluate_top_k(ranked: pd.DataFrame, actual: pd.DataFrame, *, k: int) -> dict:
    """Score frozen lists against complete actual cells; never select with actual.

    Caller supplies the dense covered actual grid, so absent cells are errors.
    Zero total yields an undefined share (None). Q1 test use is retrospective.
    """
    if ranked.empty or not isinstance(k, int) or isinstance(k, bool) or not 1 <= k <= len(ranked):
        raise ContractError("K must be between 1 and the candidate zone count")
    if ranked.pickup_location_id.duplicated().any():
        raise ContractError("candidate zones must be unique")
    if any(ranked[column].nunique(dropna=False) != 1 for column in
           ("forecast_date", "borough", "start_hour", "end_hour", "ranking_version")):
        raise ContractError("evaluation requires one date, borough and interval policy")
    scores = ranked[["predicted_trip_count", "baseline_trip_count"]].to_numpy(dtype=float)
    if not np.isfinite(scores).all() or (scores < 0).any():
        raise ContractError("ranking scores must be finite and non-negative")
    day = pd.Timestamp(ranked.forecast_date.iloc[0]).normalize()
    start, end = int(ranked.start_hour.iloc[0]), int(ranked.end_hour.iloc[0])
    # Freeze both selections before inspecting actuals.
    lists = {
        name: ranked.sort_values([column, "pickup_location_id"], ascending=[False, True]).head(k).pickup_location_id.tolist()
        for name, column in [("forecast", "predicted_trip_count"), ("d_minus_7", "baseline_trip_count")]
    }
    cells = actual.loc[
        pd.to_datetime(actual.demand_date).dt.normalize().eq(day)
        & actual.pickup_location_id.isin(ranked.pickup_location_id)
        & actual.demand_hour.isin(range(start, end))
    ].copy()
    if (cells.duplicated(["pickup_location_id", "demand_hour"]).any()
            or len(cells) != len(ranked)*(end-start)):
        raise ContractError("actual requires complete unique candidate zone-hour coverage")
    values = cells.trip_count.to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values < 0).any():
        raise ContractError("actual pickups must be finite and non-negative")
    total = float(values.sum())
    result = {}
    for name, ids in lists.items():
        captured = float(cells.loc[cells.pickup_location_id.isin(ids), "trip_count"].sum())
        result[name] = {"zone_ids": ids, "k": k, "candidate_count": len(ranked),
                        "actual_pickups": captured, "candidate_actual_pickups": total,
                        "actual_share": captured/total if total else None,
                        "tie_policy": "score descending, zone ID ascending; exactly K",
                        "ranking_version": RANKING_VERSION}
    return result
