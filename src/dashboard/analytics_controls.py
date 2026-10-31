"""Draft filters are committed together; drill-down stays inside that scope."""
from calendar import monthrange
from datetime import date

import streamlit as st


def time_scope(filters, month, day):
    start, end, borough, hours, zones = filters
    if month:
        first = date.fromisoformat(month)
        start = max(start, first)
        end = min(end, first.replace(day=monthrange(first.year, first.month)[1]))
    if day:
        selected = date.fromisoformat(day)
        if not start <= selected <= end:
            raise ValueError("Drill-down day is outside the applied scope")
        start = end = selected
    if start > end:
        raise ValueError("Drill-down month is outside the applied scope")
    return start, end, borough, hours, zones


def analytics_filters(first, last, available_months, boroughs, zones):
    default = (first, last, None, (0, 23), ())
    if "analytics_applied" not in st.session_state:
        st.session_state.analytics_applied = default
    with st.sidebar:
        st.header("Pickup filters")
        with st.form("analytics_filters"):
            start = st.date_input("From date", first, min_value=first, max_value=last)
            end = st.date_input("To date", last, min_value=first, max_value=last)
            label = st.selectbox("Borough", ["All", *boroughs], help="Pickup area, not drop-off area.")
            hours = st.slider("Pickup hours", 0, 23, (0, 23), help="Both endpoints included: 6–9 covers 06:00–09:59, New York time.")
            options = {f"{z['borough']} · {z['zone_name']} (#{z['pickup_location_id']})": z for z in zones}
            chosen = st.multiselect("Taxi zones (optional)", list(options),
                help="Leave empty for all zones in the borough. Zones are labelled by borough.")
            submitted = st.form_submit_button("Apply filters", type="primary")
        if submitted:
            borough = None if label == "All" else label
            missing = []
            cursor = start.replace(day=1)
            while cursor <= end:
                if cursor not in available_months:
                    missing.append(cursor.strftime("%m/%Y"))
                cursor = date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)
            if start > end:
                st.error("Start date must not exceed end date. Previous filters are retained.")
            elif missing:
                st.error(f"Coverage unavailable for {', '.join(missing)}. Previous filters are retained.")
            elif borough and any(options[item]["borough"] != borough for item in chosen):
                st.error("Zones must belong to the selected borough, or choose All boroughs. Previous filters are retained.")
            else:
                st.session_state.analytics_applied = (start, end, borough, tuple(hours),
                    tuple(sorted(options[item]["pickup_location_id"] for item in chosen)))
        if st.button("Reload data", help="Reload after the pipeline updates. The next load may take longer."):
            st.cache_data.clear()
            st.rerun()
    applied = st.session_state.analytics_applied
    # Coverage may change after a pipeline run or manual refresh. Never label an
    # unavailable month as zero, even if it was in an earlier applied selection.
    cursor = applied[0].replace(day=1)
    while cursor <= applied[1]:
        if cursor not in available_months:
            st.error(f"Coverage unavailable for {cursor:%m/%Y}. Select another date range.")
            st.stop()
        cursor = date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)
    return applied


def filter_caption(filters):
    start, end, borough, hours, zones = filters
    zone_label = f"{len(zones)} selected zones" if zones else "all zones"
    return (f"Applied: {start:%d/%m/%Y}–{end:%d/%m/%Y} · "
            f"{borough or 'All boroughs'} · {zone_label} · "
            f"pickup hours {hours[0]:02d}:00–{hours[1]:02d}:59 (New York).")
