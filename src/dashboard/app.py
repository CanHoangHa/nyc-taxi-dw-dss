"""Streamlit overview and OLAP views owned by warehouse/analytics engineering.

Run from the repository root with:
    streamlit run src/dashboard/app.py
"""

from __future__ import annotations

from datetime import date, timedelta
import sys
from pathlib import Path

import altair as alt
import pandas as pd
import psycopg
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dashboard.analytics_repository import AnalyticsRepository  # noqa: E402
from dss.service import DssService  # noqa: E402
from dss.ranking import rank_zone_interval  # noqa: E402
from dss.contracts import ContractError  # noqa: E402
from dashboard.analytics_controls import analytics_filters, filter_caption  # noqa: E402
from dashboard.olap_view import pickup_chart, show_olap_explorer  # noqa: E402
from dashboard.pattern_charts import show_forecast_patterns  # noqa: E402
from dashboard.forecast_controls import planning_scope  # noqa: E402
from taxi_dw.config import ConfigurationError  # noqa: E402
from taxi_dw.db import open_connection  # noqa: E402


APPROACH_LABELS = {
    "random_forest": "Random Forest",
    "hist_gradient_boosting_poisson": "Poisson gradient boosting",
    "model": "Poisson gradient boosting",
    "seasonal_naive": "Seasonal naive (D−7)",
    "same_weekday_median": "Same-weekday median",
}


@st.cache_data(ttl=300, show_spinner=False)
def reference_data():
    with open_connection() as connection:
        repository = AnalyticsRepository(connection)
        months = repository.available_months()
        bounds = (months[0], (pd.Timestamp(months[-1]) + pd.offsets.MonthEnd(0)).date()) if months else (None, None)
        return (
            bounds,
            months,
            repository.boroughs(),
            repository.zones(),
        )


@st.cache_data(ttl=300, show_spinner=False)
def overview_data(start_date, end_date, borough, hour_range, zone_ids):
    with open_connection() as connection:
        repository = AnalyticsRepository(connection)
        filters = {
            "borough": borough,
            "hour_range": hour_range,
            "zone_ids": zone_ids,
        }
        return (
            repository.summary(start_date, end_date, **filters),
            repository.olap(start_date, end_date, time_level="day", geo_level="all", **filters)[0],
            repository.olap(start_date, end_date, time_level="hour", geo_level="all", **filters)[0],
            repository.olap(start_date, end_date, time_level="all", geo_level="borough", **filters)[0],
            repository.olap(start_date, end_date, time_level="all", geo_level="zone", limit=30, **filters)[0],
        )


@st.cache_data(ttl=300, show_spinner=False)
def olap(start_date, end_date, time_level, geo_level, borough, hour_range, zone_ids, limit):
    return AnalyticsRepository().olap(
        start_date,
        end_date,
        time_level=time_level,
        geo_level=geo_level,
        borough=borough,
        hour_range=hour_range,
        zone_ids=zone_ids,
        limit=limit,
    )


def show_overview(filters):
    start_date, end_date, borough, hour_range, zone_ids = filters
    metrics, daily, hourly, by_borough, top_zones = overview_data(
        start_date, end_date, borough, hour_range, zone_ids
    )
    columns = st.columns(3)
    columns[0].metric("Valid pickups", f"{metrics['trip_count']:,}")
    calendar_days = (end_date - start_date).days + 1
    columns[1].metric("Average pickups / day", f"{metrics['trip_count'] / calendar_days:,.1f}",
                      help="Total pickups divided by the number of selected dates, including days with no pickups.")
    peak = max(hourly, key=lambda row: row['trip_count']) if hourly and metrics['trip_count'] else None
    columns[2].metric("Busiest pickup hour", f"{int(peak['demand_hour']):02d}:00" if peak else "—",
                      help="Hour with the most pickups across the selected dates. Ties use the earliest hour. New York time.")

    if not metrics["trip_count"]:
        st.info("No valid pickups match these filters.")
        return

    st.subheader("Daily pickups")
    day_frame = pd.DataFrame(daily)
    day_frame["demand_date"] = pd.to_datetime(day_frame.demand_date)
    day_frame = day_frame.set_index("demand_date").reindex(pd.date_range(start_date, end_date), fill_value=0).rename_axis("demand_date").reset_index()
    st.altair_chart(alt.Chart(day_frame).mark_line(color="#66c2ff").encode(
        x=alt.X("demand_date:T", title="Pickup date", axis=alt.Axis(format="%d/%m")),
        y=alt.Y("trip_count:Q", title="Valid pickups"),
        tooltip=[alt.Tooltip("demand_date:T", title="Date", format="%d/%m/%Y"),
                 alt.Tooltip("trip_count:Q", title="Valid pickups", format=",")],
    ).properties(height=300), width="stretch")
    left, right = st.columns(2)
    with left:
        st.subheader("Pickups by hour")
        hourly_frame = pd.DataFrame(hourly).set_index("demand_hour").reindex(range(hour_range[0],hour_range[1]+1),fill_value=0).reset_index()
        hourly_frame["Hour"] = hourly_frame.demand_hour.map(lambda hour: f"{hour:02d}:00")
        st.altair_chart(pickup_chart(hourly_frame,"Hour","Hour (New York)"),width="stretch")
    with right:
        st.subheader("Pickups by borough")
        st.altair_chart(pickup_chart(pd.DataFrame(by_borough),"borough","Borough",horizontal=True),width="stretch")
    zone_heading, zone_limit = st.columns([5, 1])
    zone_heading.subheader("Top pickup zones")
    top_n = zone_limit.selectbox("Zones to display", [10, 20, 30],
        format_func=lambda count: f"Top {count}", key="overview_top_n", label_visibility="collapsed")
    zone_frame = pd.DataFrame(top_zones[:top_n])
    zone_frame["taxi_zone"] = (
        zone_frame["zone_name"] + " (#" + zone_frame["pickup_location_id"].astype(str) + ")"
    )
    st.altair_chart(pickup_chart(zone_frame,"taxi_zone","Taxi zone",horizontal=True),width="stretch")


def dss_forecasts(forecast_date):
    service = DssService()
    run, rows, metrics = service.forecast_snapshot(forecast_date)
    return run, rows, metrics, service.ranking_zones()


def show_dss():
    """Render persisted, versioned forecasts without training inside the UI."""

    service = DssService()
    dates = service.available_forecast_dates()
    if not dates:
        st.info("No forecasts available. Publish a forecast before opening this view.")
        return
    initial_date = st.session_state.get("planning_applied", (dates[0],))[0]
    if initial_date not in dates:
        initial_date = dates[0]
    run, rows, metrics, zone_reference = dss_forecasts(initial_date)
    if run is None or rows.empty:
        st.info("No complete forecast is available for this date.")
        return
    forecast_date, borough_label, forecast_hours, zone_ids, review_limit = planning_scope(dates, zone_reference)
    if forecast_date != initial_date:
        run, rows, metrics, zone_reference = dss_forecasts(forecast_date)
        if run is None or rows.empty:
            st.info("No complete forecast is available for this date.")
            return

    try:
        ranking = rank_zone_interval(
            rows, borough=borough_label, start_hour=forecast_hours[0],
            end_hour=forecast_hours[1], zone_ids=zone_ids, zone_reference=zone_reference,
        )
    except ContractError as error:
        st.warning(str(error))
        return
    mask = rows["demand_hour"].ge(forecast_hours[0]) & rows["demand_hour"].lt(forecast_hours[1])
    mask &= rows["is_actionable"] & rows["pickup_location_id"].between(1, 263)
    if borough_label != "All":
        mask &= rows["borough"].eq(borough_label)
    if zone_ids:
        mask &= rows["pickup_location_id"].isin(zone_ids)
    filtered = rows.loc[mask].copy()
    if filtered.empty:
        st.info("No forecast matches these filters.")
        return

    high_count = int(filtered["demand_level"].eq("High").sum())
    columns = st.columns(3)
    columns[0].metric(
        "Forecast pickups", f"{filtered['predicted_trip_count'].sum():,.1f}"
    )
    columns[1].metric("High-demand zone-hours", f"{high_count:,}",
                      help="Zone-hour pairs forecast at or above their own historical p75; not a count of distinct zones.")
    model_name = str(run["model_name"])
    columns[2].metric(
        "Forecast method", APPROACH_LABELS.get(model_name, model_name)
    )
    is_refit = run.get("fit_kind", "selection") == "refit"
    def show_date(value):
        return pd.Timestamp(value).strftime("%d/%m/%Y") if value is not None else "Not recorded"
    fit_start = run.get("fit_start_date") or run.get("train_start_date")
    fit_end = run.get("fit_end_date") or run.get("train_end_date")
    fit_seconds = run.get("fit_seconds")
    duration = f"{fit_seconds:.2f} seconds" if fit_seconds is not None else "Not recorded"
    st.caption(f"{forecast_date:%d %b %Y} · {borough_label} · "
               f"{forecast_hours[0]:02d}:00–{forecast_hours[1]:02d}:00 (end excluded)")
    if is_refit and date(2024, 4, 1) <= forecast_date <= date(2024, 4, 30):
        st.info(f"Historical demo: forecasts use history through {forecast_date - timedelta(days=1):%d %b %Y}; "
                "April actuals are already available.")
    if model_name in {"seasonal_naive", "same_weekday_median"}:
        st.info(
            "The baseline had the lowest validation WAPE and was selected for this run."
        )

    st.subheader("Zones to review")
    st.caption("Areas ranked by forecast pickup volume. Combine with fleet availability when planning service.")
    st.caption(f"Showing {min(review_limit, len(ranking))} of {len(ranking)} zones in the applied scope.")
    if not ranking.empty:
        st.dataframe(
            ranking.head(review_limit)[["rank", "pickup_location_id", "zone_name", "predicted_trip_count",
                     "baseline_trip_count"]],
            hide_index=True, width="stretch",
            column_config={"rank": "Rank", "pickup_location_id": "Zone ID", "zone_name": "Taxi zone",
                           "predicted_trip_count": st.column_config.NumberColumn("Forecast pickups", format="%.1f"),
                           "baseline_trip_count": st.column_config.NumberColumn("Last week (D−7)", format="%.0f")},
        )

    st.subheader("Hourly forecast vs. last week")
    hourly = filtered.groupby("demand_hour", as_index=False)[
        ["predicted_trip_count", "baseline_trip_count"]
    ].sum()
    hourly = hourly.melt(
        id_vars="demand_hour",
        var_name="series",
        value_name="trip_count",
    )
    hourly["series"] = hourly["series"].map(
        {
            "predicted_trip_count": "Forecast",
            "baseline_trip_count": "Last week (D−7)",
        }
    )
    chart = (
        alt.Chart(hourly)
        .mark_line(point=True, strokeWidth=2.5)
        .encode(
            x=alt.X(
                "demand_hour:O",
                title="Hour (New York)",
                sort=list(range(24)),
                axis=alt.Axis(labelAngle=0),
            ),
            y=alt.Y(
                "trip_count:Q",
                title="Pickups",
                scale=alt.Scale(zero=True),
            ),
            color=alt.Color("series:N", title=None),
            strokeDash=alt.StrokeDash("series:N", title=None),
            tooltip=[
                alt.Tooltip("demand_hour:O", title="Hour"),
                alt.Tooltip("series:N", title="Series"),
                alt.Tooltip("trip_count:Q", title="Pickup", format=",.1f"),
            ],
        )
        .properties(height=360)
    )
    st.altair_chart(chart, width="stretch")

    show_forecast_patterns(ranking, filtered, forecast_hours[0], forecast_hours[1], k=review_limit)

    display_columns = [
        "demand_hour",
        "borough",
        "pickup_location_id",
        "zone_name",
        "predicted_trip_count",
        "baseline_trip_count",
        "demand_ratio",
        "demand_level",
    ]
    with st.expander("Hourly details"):
        st.dataframe(
            filtered.loc[:, display_columns], width="stretch", hide_index=True,
            column_config={
                "demand_hour": st.column_config.NumberColumn("Hour", format="%d"),
                "borough": "Borough", "pickup_location_id": "Zone ID", "zone_name": "Taxi zone",
                "predicted_trip_count": st.column_config.NumberColumn("Forecast", format="%.1f"),
                "baseline_trip_count": st.column_config.NumberColumn("D−7", format="%.0f"),
                "demand_ratio": st.column_config.NumberColumn("vs. last week", format="%.2f"),
                "demand_level": "Demand level",
            },
        )
    with st.expander("How priorities work"):
        st.write("Zones are ranked by forecast pickups, with equal totals sharing a rank. "
                 "This identifies pickup concentration, not the number of taxis to dispatch.")
        st.write("Hourly demand levels compare each zone-hour against its own training history: "
                 "High ≥ p75; Medium ≥ p50 and below p75; Low otherwise. Zero forecasts are Low. "
                 "These levels do not determine the zone ranking.")
    with st.expander("Model details"):
        st.caption(f"{'Refitted model' if is_refit else 'Original model'} · "
                   f"Fit data: {show_date(fit_start)}–{show_date(fit_end)} · Fit time: {duration}.")
        st.caption(f"Selection train: {show_date(run.get('train_start_date'))}–{show_date(run.get('train_end_date'))}; "
                   f"validation: {show_date(run.get('validation_start_date'))}–{show_date(run.get('validation_end_date'))}.")
        st.caption(f"Model {run['model_version']} · Features {run['feature_version']} · "
                   f"Recommendation policy {run['recommendation_version']}")
        st.caption(f"Run ID: {run['run_id']}")

    validation = metrics.get("selection_validation", metrics.get("validation", {})) if isinstance(metrics, dict) else {}
    if isinstance(validation, dict) and validation:
        metric_rows = []
        for approach, values in validation.items():
            if not isinstance(values, dict):
                continue
            metric_rows.append(
                {
                    "Method": APPROACH_LABELS.get(approach, approach),
                    "Selected": approach == model_name
                    or (
                        approach == "model"
                        and model_name == "hist_gradient_boosting_poisson"
                    ),
                    "MAE": values.get("mae"),
                    "RMSE": values.get("rmse"),
                    "WAPE (%)": 100 * values["wape"] if values.get("wape") is not None else None,
                }
            )
        with st.expander("Model selection validation"):
            if is_refit:
                st.caption("Original model selection scores; these do not evaluate the refitted model.")
            st.dataframe(
                pd.DataFrame(metric_rows),
                width="stretch",
                hide_index=True,
                column_config={
                    "MAE": st.column_config.NumberColumn(format="%.3f"),
                    "RMSE": st.column_config.NumberColumn(format="%.3f"),
                    "WAPE (%)": st.column_config.NumberColumn(format="%.2f%%"),
                },
            )
    if is_refit:
        with st.expander("April 2024 evaluation"):
            st.write(
                "Day-ahead evaluation on 189,360 zone-hours, 1–30 April: "
                "WAPE: refitted RF 17.87%; original RF 18.32%; median 18.06%; D−7 21.85%. "
                "Each forecast uses history through D−1. April was not used for selection or tuning."
            )
            st.caption(
                "Ranking improved only slightly over D−7; this does not establish dispatch effectiveness. "
                "These full-month scores do not describe the selected day or hour."
            )


def main():
    st.set_page_config(page_title="NYC Taxi Analytics", layout="wide")
    st.title("NYC Yellow Taxi | Pickup Analytics")
    st.caption("Valid yellow taxi pickups · New York local time")

    view = st.radio(
        "View", ["Overview", "OLAP", "Forecast & priorities"], horizontal=True
    )
    if view == "Forecast & priorities":
        try:
            show_dss()
        except (psycopg.Error, ConfigurationError, ValueError) as error:
            st.error(f"Unable to load forecasts: {error}")
        return

    try:
        with st.spinner("Loading data coverage…"):
            (first_date, last_date), available_months, boroughs, zones = reference_data()
    except (psycopg.Error, ConfigurationError) as error:
        st.error(f"Unable to connect to analytics data: {error}")
        st.stop()
    if first_date is None:
        st.info("No reconciled data is available. Run the data pipeline first.")
        st.stop()

    filters = analytics_filters(first_date, last_date, available_months, boroughs, zones)
    st.caption(filter_caption(filters))
    try:
        if view == "Overview":
            show_overview(filters)
        else:
            show_olap_explorer(filters, olap)
    except (psycopg.Error, ConfigurationError, ValueError) as error:
        st.error(f"Unable to load analytics: {error}")


if __name__ == "__main__":
    main()
