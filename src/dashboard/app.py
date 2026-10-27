"""Streamlit overview and OLAP views owned by warehouse/analytics engineering.

Run from the repository root with:
    streamlit run src/dashboard/app.py
"""

from __future__ import annotations

from datetime import date
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
from taxi_dw.config import ConfigurationError  # noqa: E402
from taxi_dw.db import open_connection  # noqa: E402


TIME_LABELS = {
    "Tất cả ngày": "all",
    "Theo tháng": "month",
    "Theo ngày": "day",
    "Theo giờ trong ngày": "hour",
    "Ngày và giờ": "day_hour",
}
GEO_LABELS = {
    "Tất cả vùng": "all",
    "Theo borough": "borough",
    "Theo taxi zone": "zone",
}
APPROACH_LABELS = {
    "random_forest": "Random Forest",
    "hist_gradient_boosting_poisson": "Poisson gradient boosting",
    "model": "Poisson gradient boosting",
    "seasonal_naive": "Seasonal naive (D−7)",
    "same_weekday_median": "Median 4 tuần cùng thứ",
}


@st.cache_data(ttl=300, show_spinner=False)
def reference_data():
    with open_connection() as connection:
        repository = AnalyticsRepository(connection)
        return (
            repository.date_bounds(),
            repository.available_months(),
            repository.boroughs(),
            repository.zones(),
        )


def months_between(start_date: date, end_date: date) -> list[date]:
    months = []
    year, month = start_date.year, start_date.month
    while (year, month) <= (end_date.year, end_date.month):
        months.append(date(year, month, 1))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


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
            repository.olap(start_date, end_date, time_level="all", geo_level="zone", limit=10, **filters)[0],
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
    columns[0].metric("Chuyến đón hợp lệ", f"{metrics['trip_count']:,}")
    columns[1].metric("Vùng có chuyến đón", f"{metrics['active_zones']:,}")
    columns[2].metric("Ngày có chuyến đón", f"{metrics['active_days']:,}")

    if not metrics["trip_count"]:
        st.info("Không có chuyến đón hợp lệ trong bộ lọc này.")
        return

    st.subheader("Nhu cầu đón theo ngày")
    st.line_chart(pd.DataFrame(daily), x="demand_date", y="trip_count")
    left, right = st.columns(2)
    with left:
        st.subheader("Theo giờ địa phương New York")
        st.bar_chart(pd.DataFrame(hourly), x="demand_hour", y="trip_count")
    with right:
        st.subheader("Theo borough")
        st.bar_chart(pd.DataFrame(by_borough), x="borough", y="trip_count")
    st.subheader("10 taxi zone có nhiều chuyến đón nhất")
    zone_frame = pd.DataFrame(top_zones)
    zone_frame["taxi_zone"] = (
        zone_frame["zone_name"] + " (#" + zone_frame["pickup_location_id"].astype(str) + ")"
    )
    st.bar_chart(zone_frame, x="taxi_zone", y="trip_count", horizontal=True)


def show_olap(filters):
    start_date, end_date, borough, hour_range, zone_ids = filters
    st.write(
        "Đổi cấp thời gian hoặc địa lý để roll-up/drill-down. Bộ lọc ngày, "
        "borough, giờ và taxi zone ở thanh bên dùng cho slice/dice."
    )
    left, right = st.columns(2)
    with left:
        time_label = st.selectbox("Cấp thời gian", list(TIME_LABELS), index=2)
    with right:
        geo_label = st.selectbox("Cấp địa lý", list(GEO_LABELS), index=1)
    rows, truncated = olap(
        start_date,
        end_date,
        TIME_LABELS[time_label],
        GEO_LABELS[geo_label],
        borough,
        hour_range,
        zone_ids,
        5000,
    )
    if truncated:
        st.warning("Chỉ hiển thị 5.000 nhóm đầu. Hãy thu hẹp bộ lọc để xem đủ kết quả.")
    if not rows or (len(rows) == 1 and rows[0]["trip_count"] == 0):
        st.info("Không có chuyến đón hợp lệ trong bộ lọc này.")
        return
    frame = pd.DataFrame(rows)
    st.dataframe(frame, width="stretch", hide_index=True)
    st.download_button(
        "Tải bảng đang hiển thị (CSV)",
        data=frame.to_csv(index=False).encode("utf-8-sig"),
        file_name="nyc_taxi_olap.csv",
        mime="text/csv",
    )
    if not truncated:
        st.caption(f"Tổng các nhóm đang hiển thị: {frame['trip_count'].sum():,} chuyến.")


@st.cache_data(ttl=300, show_spinner=False)
def dss_forecasts(forecast_date):
    service = DssService()
    return (
        service.latest_run_summary(forecast_date),
        service.ranked_recommendations(forecast_date),
        service.model_metrics(forecast_date),
        service.ranking_zones(),
    )


def show_dss():
    """Render persisted, versioned forecasts without training inside the UI."""

    service = DssService()
    dates = service.available_forecast_dates()
    if not dates:
        st.info(
            "Chưa có forecast Gate C. Hãy chạy DSS train/forecast và migration "
            "sql/003_create_dss_tables.sql trước."
        )
        return
    with st.sidebar:
        st.header("Bộ lọc dự báo")
        forecast_date = st.selectbox(
            "Ngày dự báo", dates, format_func=lambda value: value.strftime("%d/%m/%Y")
        )
    run, rows, metrics, zone_reference = dss_forecasts(forecast_date)
    if run is None or rows.empty:
        st.info("Không có forecast hoàn chỉnh cho ngày đã chọn.")
        return

    operational_zones = zone_reference.loc[zone_reference["is_actionable"]]
    boroughs = sorted(operational_zones["borough"].dropna().unique().tolist())
    with st.sidebar:
        borough_label = st.selectbox("Borough dự báo", boroughs)
        forecast_hours = st.slider(
            "Khoảng giờ dự báo [bắt đầu, kết thúc)", min_value=0, max_value=24, value=(6, 10)
        )
        st.caption("06:00–10:00 gồm giờ 6, 7, 8, 9. API chi tiết cũ vẫn bao gồm hai đầu.")
        available_zones = operational_zones
        if borough_label != "Tất cả":
            available_zones = operational_zones.loc[operational_zones["borough"].eq(borough_label)]
        zone_options = {
            f"{row.borough} · {row.zone_name} (#{row.pickup_location_id})": int(
                row.pickup_location_id
            )
            for row in available_zones[
                ["borough", "zone_name", "pickup_location_id"]
            ]
            .drop_duplicates()
            .sort_values(["borough", "zone_name"])
            .itertuples(index=False)
        }
        chosen_zones = st.multiselect(
            "Taxi zone (tùy chọn)",
            list(zone_options),
            key=f"dss_zone_filter_{borough_label}",
        )
        zone_ids = tuple(zone_options[label] for label in chosen_zones)
        if st.button("Làm mới dữ liệu", key="refresh_dss"):
            st.cache_data.clear()
            st.rerun()

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
    if borough_label != "Tất cả":
        mask &= rows["borough"].eq(borough_label)
    if zone_ids:
        mask &= rows["pickup_location_id"].isin(zone_ids)
    filtered = rows.loc[mask].copy()
    if filtered.empty:
        st.info("Không có forecast trong bộ lọc đã chọn.")
        return

    high_count = int(filtered["demand_level"].eq("High").sum())
    columns = st.columns(3)
    columns[0].metric(
        "Tổng pickup dự báo", f"{filtered['predicted_trip_count'].sum():,.1f}"
    )
    columns[1].metric("Zone-hour mức High", f"{high_count:,}")
    model_name = str(run["model_name"])
    columns[2].metric(
        "Phương pháp được chọn", APPROACH_LABELS.get(model_name, model_name)
    )
    st.caption(
        f"Model {run['model_version']} · feature {run['feature_version']} · "
        f"recommendation {run['recommendation_version']}"
    )
    if model_name in {"seasonal_naive", "same_weekday_median"}:
        st.info(
            "Baseline này được chọn vì có WAPE validation thấp nhất; hệ thống không "
            "ép mô hình học máy thắng khi số liệu chưa chứng minh điều đó."
        )

    st.subheader("Dự báo so với seasonal-naive D−7 theo giờ")
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
            "predicted_trip_count": "Dự báo được chọn",
            "baseline_trip_count": "Baseline D−7",
        }
    )
    chart = (
        alt.Chart(hourly)
        .mark_line(point=True, strokeWidth=2.5)
        .encode(
            x=alt.X(
                "demand_hour:O",
                title="Giờ địa phương New York",
                sort=list(range(24)),
                axis=alt.Axis(labelAngle=0),
            ),
            y=alt.Y(
                "trip_count:Q",
                title="Số pickup dự báo",
                scale=alt.Scale(zero=True),
            ),
            color=alt.Color("series:N", title=None),
            strokeDash=alt.StrokeDash("series:N", title=None),
            tooltip=[
                alt.Tooltip("demand_hour:O", title="Giờ"),
                alt.Tooltip("series:N", title="Chuỗi"),
                alt.Tooltip("trip_count:Q", title="Pickup", format=",.1f"),
            ],
        )
        .properties(height=360)
    )
    st.altair_chart(chart, width="stretch")

    st.subheader("Xếp hạng zone theo tổng pickup dự báo")
    st.caption(
        "Hạng theo tổng dự báo trong khoảng giờ; đồng tổng cùng hạng. "
        "Zone ID chỉ ổn định thứ tự hiển thị. Đây là nhận diện nơi có pickup, "
        "không phải tối ưu điều phối, thiếu hụt xe hay số taxi cần điều tới."
    )
    if not ranking.empty:
        st.dataframe(
            ranking[["rank", "pickup_location_id", "zone_name", "predicted_trip_count",
                     "baseline_trip_count", "hour_count", "ranking_reason"]],
            hide_index=True, width="stretch",
            column_config={"rank": "Hạng", "pickup_location_id": "Zone ID", "zone_name": "Taxi zone",
                           "predicted_trip_count": "Tổng pickup dự báo", "baseline_trip_count": "Tổng D−7",
                           "hour_count": "Số giờ", "ranking_reason": "Giải thích"},
        )
    st.subheader("Chi tiết từng giờ và nhãn nhu cầu")
    display_columns = [
        "demand_hour",
        "borough",
        "pickup_location_id",
        "zone_name",
        "predicted_trip_count",
        "baseline_trip_count",
        "demand_ratio",
        "demand_level",
        "recommendation",
        "recommendation_reason",
    ]
    st.dataframe(
        filtered.loc[:, display_columns],
        width="stretch",
        hide_index=True,
        column_config={
            "demand_hour": st.column_config.NumberColumn("Giờ", format="%d"),
            "borough": "Borough",
            "pickup_location_id": st.column_config.NumberColumn(
                "Zone ID", format="%d"
            ),
            "zone_name": "Taxi zone",
            "predicted_trip_count": st.column_config.NumberColumn("Dự báo", format="%.1f"),
            "baseline_trip_count": st.column_config.NumberColumn("D−7", format="%.1f"),
            "demand_ratio": st.column_config.NumberColumn("Tỷ lệ", format="%.2f"),
            "demand_level": "Mức nhu cầu",
            "recommendation": st.column_config.TextColumn("Khuyến nghị", width="large"),
            "recommendation_reason": st.column_config.TextColumn(
                "Lý do", width="large"
            ),
        },
    )

    validation = metrics.get("validation", {}) if isinstance(metrics, dict) else {}
    if isinstance(validation, dict) and validation:
        metric_rows = []
        for approach, values in validation.items():
            if not isinstance(values, dict):
                continue
            metric_rows.append(
                {
                    "Phương pháp": APPROACH_LABELS.get(approach, approach),
                    "Được chọn": approach == model_name
                    or (
                        approach == "model"
                        and model_name == "hist_gradient_boosting_poisson"
                    ),
                    "MAE": values.get("mae"),
                    "RMSE": values.get("rmse"),
                    "WAPE (%)": 100 * values["wape"] if values.get("wape") is not None else None,
                }
            )
        with st.expander("Chi tiết đánh giá validation"):
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
    st.caption(
        f"Run {run['run_id']} · dữ liệu đọc từ Gate C, không train lại trong dashboard."
    )


def main():
    st.set_page_config(page_title="NYC Taxi — phân tích", layout="wide")
    st.title("NYC Yellow Taxi | Phân tích nhu cầu đón")
    st.caption(
        "Chỉ đếm chuyến hợp lệ đã nạp và dựng mart. Giờ là giờ địa phương New York; "
        "thiếu tổ hợp ngoài các tháng đã nạp không được hiểu là 0 chuyến."
    )

    view = st.radio(
        "Góc nhìn", ["Tổng quan", "OLAP", "Dự báo & khuyến nghị"], horizontal=True
    )
    if view == "Dự báo & khuyến nghị":
        try:
            show_dss()
        except (psycopg.Error, ConfigurationError, ValueError) as error:
            st.error(f"Không thể đọc forecast Gate C: {error}")
        return

    try:
        (first_date, last_date), available_months, boroughs, zones = reference_data()
    except (psycopg.Error, ConfigurationError) as error:
        st.error(f"Không đọc được mart. Hãy kiểm tra PostgreSQL, .env và dbt run: {error}")
        st.stop()
    if first_date is None:
        st.info("Chưa có tháng nào được đối soát đủ qua audit, fact và mart. Hãy chạy dbt trước.")
        st.stop()

    with st.sidebar:
        st.header("Bộ lọc")
        start_date = st.date_input("Từ ngày", first_date, min_value=first_date, max_value=last_date)
        end_date = st.date_input("Đến ngày", last_date, min_value=first_date, max_value=last_date)
        borough_label = st.selectbox("Borough", ["Tất cả", *boroughs])
        borough = None if borough_label == "Tất cả" else borough_label
        hour_range = st.slider("Giờ đón", min_value=0, max_value=23, value=(0, 23))
        available_zones = (
            zones
            if borough is None
            else [zone for zone in zones if zone["borough"] == borough]
        )
        zone_options = {
            f"{zone['borough']} · {zone['zone_name']} (#{zone['pickup_location_id']})": zone[
                "pickup_location_id"
            ]
            for zone in available_zones
        }
        chosen_zones = st.multiselect(
            "Taxi zone (tùy chọn)",
            list(zone_options),
            key=f"analytics_zone_filter_{borough_label}",
        )
        zone_ids = tuple(zone_options[label] for label in chosen_zones)
        if st.button("Làm mới dữ liệu"):
            st.cache_data.clear()
            st.rerun()

    if start_date > end_date:
        st.error("Ngày bắt đầu phải không sau ngày kết thúc.")
        st.stop()
    missing_months = [
        month for month in months_between(start_date, end_date) if month not in available_months
    ]
    if missing_months:
        missing_labels = ", ".join(month.strftime("%m/%Y") for month in missing_months)
        st.warning(
            f"Chưa xác nhận đủ dữ liệu cho tháng {missing_labels}. "
            "Khoảng này chưa thể được diễn giải là 0 chuyến."
        )
        st.stop()
    filters = (start_date, end_date, borough, hour_range, zone_ids)
    try:
        if view == "Tổng quan":
            show_overview(filters)
        else:
            show_olap(filters)
    except (psycopg.Error, ConfigurationError, ValueError) as error:
        st.error(f"Không thể chạy truy vấn phân tích: {error}")


if __name__ == "__main__":
    main()
