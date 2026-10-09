"""Streamlit overview and OLAP views owned by warehouse/analytics engineering.

Run from the repository root with:
    streamlit run src/dashboard/app.py
"""

from __future__ import annotations

from datetime import date
import sys
from pathlib import Path

import pandas as pd
import psycopg
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dashboard.analytics_repository import AnalyticsRepository  # noqa: E402
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


def main():
    st.set_page_config(page_title="NYC Taxi — phân tích", layout="wide")
    st.title("NYC Yellow Taxi | Phân tích nhu cầu đón")
    st.caption(
        "Chỉ đếm chuyến hợp lệ đã nạp và dựng mart. Giờ là giờ địa phương New York; "
        "thiếu tổ hợp ngoài các tháng đã nạp không được hiểu là 0 chuyến."
    )

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
        zone_options = {
            f"{zone['borough']} · {zone['zone_name']} (#{zone['pickup_location_id']})": zone[
                "pickup_location_id"
            ]
            for zone in zones
        }
        chosen_zones = st.multiselect("Taxi zone (tùy chọn)", list(zone_options))
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
    view = st.radio("Góc nhìn", ["Tổng quan", "OLAP"], horizontal=True)
    try:
        if view == "Tổng quan":
            show_overview(filters)
        else:
            show_olap(filters)
    except (psycopg.Error, ConfigurationError, ValueError) as error:
        st.error(f"Không thể chạy truy vấn phân tích: {error}")


if __name__ == "__main__":
    main()
