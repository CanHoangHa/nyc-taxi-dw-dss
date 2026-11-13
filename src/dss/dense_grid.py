"""Build a dense daily hour-by-zone demand series from the sparse Gate B mart."""

from __future__ import annotations

from datetime import date

import pandas as pd

from dss.contracts import (
    ContractError,
    DEMAND_GRAIN,
    covered_dates,
    require_covered_range,
    validate_coverage,
    validate_sparse_demand,
    validate_zones,
)


def build_dense_demand(
    sparse_demand: pd.DataFrame,
    coverage: pd.DataFrame,
    zones: pd.DataFrame,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
) -> pd.DataFrame:
    """Zero-fill eligible zone-hour cells only inside reconciled coverage."""

    sparse = validate_sparse_demand(sparse_demand)
    normalized_coverage = validate_coverage(coverage)
    eligible_zones = validate_zones(zones)
    if normalized_coverage.empty:
        raise ContractError("at least one reconciled coverage month is required")
    if eligible_zones.empty:
        raise ContractError("at least one recommendation-eligible zone is required")

    if start_date is None and end_date is None:
        dates = covered_dates(normalized_coverage)
    elif start_date is not None and end_date is not None:
        dates = require_covered_range(normalized_coverage, start_date, end_date)
    else:
        raise ContractError("start_date and end_date must be provided together")

    actionable_sparse = sparse.loc[sparse["is_recommendation_eligible"]].copy()
    requested_dates = pd.Index(dates)
    outside = actionable_sparse.loc[
        ~actionable_sparse["demand_date"].isin(requested_dates)
    ]
    if start_date is None and not outside.empty:
        raise ContractError("sparse demand contains rows outside reconciled coverage")
    actionable_sparse = actionable_sparse.loc[
        actionable_sparse["demand_date"].isin(requested_dates)
    ]

    unknown_keys = set(actionable_sparse["pickup_zone_key"]) - set(
        eligible_zones["pickup_zone_key"]
    )
    if unknown_keys:
        raise ContractError("sparse demand contains eligible zones absent from zone contract")

    grid = pd.MultiIndex.from_product(
        [dates, range(24), eligible_zones["pickup_zone_key"]],
        names=list(DEMAND_GRAIN),
    ).to_frame(index=False)
    grid["demand_hour"] = grid["demand_hour"].astype("int8")
    grid = grid.merge(
        eligible_zones,
        on="pickup_zone_key",
        how="left",
        validate="many_to_one",
    )
    counts = actionable_sparse.loc[:, [*DEMAND_GRAIN, "trip_count"]]
    dense = grid.merge(
        counts,
        on=list(DEMAND_GRAIN),
        how="left",
        validate="one_to_one",
    )
    dense["trip_count"] = dense["trip_count"].fillna(0).astype("int64")

    expected_rows = len(dates) * 24 * len(eligible_zones)
    if len(dense) != expected_rows:
        raise RuntimeError(
            f"dense-grid row count mismatch: expected {expected_rows}, got {len(dense)}"
        )
    if dense.duplicated(list(DEMAND_GRAIN)).any():
        raise RuntimeError("dense-grid grain is not unique")
    if dense["trip_count"].sum() != actionable_sparse["trip_count"].sum():
        raise RuntimeError("dense-grid trip total does not reconcile to eligible sparse demand")

    return dense.sort_values(list(DEMAND_GRAIN), ignore_index=True)
