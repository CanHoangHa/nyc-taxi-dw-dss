"""Dashboard-facing DSS use cases, separate from Streamlit widgets."""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

import pandas as pd

from dss.contracts import ContractError
from dss.persistence import ForecastRepository
from dss.ranking import rank_zone_interval


class DssService:
    def __init__(self, repository: ForecastRepository | None = None):
        self.repository = repository or ForecastRepository()

    def available_forecast_dates(self) -> list[date]:
        return self.repository.available_forecast_dates()

    def ranking_zones(self) -> pd.DataFrame:
        return self.repository.ranking_zones()

    def latest_run_summary(self, forecast_date: date) -> dict[str, Any] | None:
        return self.repository.latest_run(forecast_date)

    def forecast_snapshot(self, forecast_date: date) -> tuple[dict | None, pd.DataFrame, dict]:
        """Resolve latest once so a concurrent publication cannot mix runs."""
        run = self.repository.latest_run(forecast_date)
        if run is None:
            return None, pd.DataFrame(), {}
        rows = self.repository.read_forecasts(UUID(str(run["run_id"])), forecast_date=forecast_date)
        metrics = run.get("metrics_json", {})
        return run, rows, metrics if isinstance(metrics, dict) else {}

    def ranked_recommendations(
        self,
        forecast_date: date,
        *,
        borough: str | None = None,
        hour_range: tuple[int, int] = (0, 23),
        zone_ids: tuple[int, ...] = (),
    ) -> pd.DataFrame:
        """Return the latest run's actionable rows ordered by decision priority."""

        if not 0 <= hour_range[0] <= hour_range[1] <= 23:
            raise ContractError("hour range must be within 0..23")
        run = self.repository.latest_run(forecast_date)
        if run is None:
            return pd.DataFrame()
        rows = self.repository.read_forecasts(
            UUID(str(run["run_id"])), forecast_date=forecast_date
        )
        if rows.empty:
            return rows
        mask = rows["demand_hour"].between(*hour_range)
        if borough is not None:
            mask &= rows["borough"].eq(borough)
        if zone_ids:
            mask &= rows["pickup_location_id"].isin(zone_ids)
        result = rows.loc[mask].copy()
        priority = {"High": 0, "Medium": 1, "Low": 2, "Not applicable": 3}
        result["_priority"] = result["demand_level"].map(priority).fillna(4)
        return result.sort_values(
            ["_priority", "predicted_trip_count", "demand_hour"],
            ascending=[True, False, True],
            ignore_index=True,
        ).drop(columns="_priority")

    def zone_hour_detail(
        self, forecast_date: date, zone_id: int
    ) -> pd.DataFrame:
        return self.ranked_recommendations(
            forecast_date, zone_ids=(zone_id,)
        ).sort_values("demand_hour", ignore_index=True)

    def zone_ranking(
        self, forecast_date: date, *, borough: str,
        start_hour: int = 0, end_hour: int = 24, zone_ids: tuple[int, ...] = (),
    ) -> pd.DataFrame:
        """One row per actionable zone in [start_hour, end_hour).

        The legacy ranked_recommendations API retains inclusive hourly behavior.
        """
        run = self.repository.latest_run(forecast_date)
        if run is None:
            return pd.DataFrame()
        rows = self.repository.read_forecasts(UUID(str(run["run_id"])), forecast_date=forecast_date)
        return rank_zone_interval(rows, borough=borough, start_hour=start_hour,
                                  end_hour=end_hour, zone_ids=zone_ids,
                                  zone_reference=self.ranking_zones())

    def model_metrics(self, forecast_date: date) -> dict[str, Any]:
        run = self.repository.latest_run(forecast_date)
        if run is None:
            return {}
        metrics = run.get("metrics_json", {})
        return metrics if isinstance(metrics, dict) else {}
