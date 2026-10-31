"""Chart-first OLAP: independent time and geography hierarchies, shared scope."""
from datetime import date

import altair as alt
import pandas as pd
import streamlit as st

from dashboard.analytics_controls import time_scope
from dashboard.pattern_charts import show_weekday_pattern


def pickup_chart(frame, field, title, *, horizontal=False, selectable=False):
    """Readable labels and exact values; optional single-node drill selection."""
    base = alt.Chart(frame).mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
    quantity = alt.Y("trip_count:Q", title="Valid pickups", axis=alt.Axis(format=",.0f"))
    category = alt.X(f"{field}:N", title=title, sort=None, axis=alt.Axis(labelAngle=0))
    if horizontal:
        maximum = float(frame.trip_count.max()) if len(frame) else 0
        chart = base.encode(x=alt.X("trip_count:Q", title="Valid pickups",
                                    scale=alt.Scale(domain=[0, max(1, maximum * 1.16)]),
                                    axis=alt.Axis(format=",.0f")),
                            y=alt.Y(f"{field}:N", title=None, sort="-x",
                                    axis=alt.Axis(labelLimit=280, labelOverlap=False)))
    else:
        chart = base.encode(x=category, y=quantity)
    chart = chart.encode(tooltip=[alt.Tooltip(f"{field}:N", title=title),
                                  alt.Tooltip("trip_count:Q", title="Valid pickups", format=",")])
    if selectable:
        choice = alt.selection_point(name="drill", fields=["node"], toggle=False, on="click", clear="dblclick")
        chart = chart.add_params(choice).encode(color=alt.condition(choice, alt.value("#66c2ff"), alt.value("#35546b")))
    if horizontal:
        text_color = "#e2e8f0" if st.context.theme.type == "dark" else "#334155"
        values = alt.Chart(frame).mark_text(align="left", baseline="middle", dx=6,
                                           color=text_color, fontSize=12).encode(
            x="trip_count:Q", y=alt.Y(f"{field}:N", sort="-x"),
            text=alt.Text("trip_count:Q", format=",.0f"),
        )
        chart = chart + values
    return chart.properties(height=max(250, 30 * len(frame)) if horizontal else 300)


def _query(query, filters, time_level, geo_level):
    start, end, borough, hours, zones = filters
    rows, truncated = query(start, end, time_level, geo_level, borough, hours, zones, 5000)
    if truncated:
        st.warning("More than 5,000 groups. Narrow the filters to view complete results.")
    return pd.DataFrame(rows), truncated


def _time_frame(frame, scope, level):
    start, end, _, hours, _ = scope
    if level == "month":
        field = "demand_month"
        index = pd.date_range(start.replace(day=1), end.replace(day=1), freq="MS")
        label = lambda value: value.strftime("%m/%Y")
    elif level == "day":
        field = "demand_date"
        index = pd.date_range(start, end)
        label = lambda value: value.strftime("%d/%m")
    else:
        field = "demand_hour"
        index = pd.Index(range(hours[0], hours[1] + 1))
        label = lambda value: f"{value:02d}:00"
    if frame.empty:
        series = pd.Series(0, index=index, dtype="int64")
    else:
        values = frame.copy()
        if level != "hour":
            values[field] = pd.to_datetime(values[field])
        series = values.set_index(field).trip_count.reindex(index, fill_value=0)
    return pd.DataFrame({"node": [v.strftime("%Y-%m-%d") if level != "hour" else str(v) for v in index],
                         "Time": [label(v) for v in index], "trip_count": series.to_numpy()})


def _clicked(event):
    # selection_point(fields=["node"]) returns a list of selected row dictionaries.
    selected = event.get("selection", {}).get("drill", []) if event else []
    return selected[0].get("node") if selected else None


def show_olap_explorer(filters, query):
    fingerprint = repr(filters)
    if st.session_state.get("olap_filters") != fingerprint:
        st.session_state.olap_filters = fingerprint
        st.session_state.olap_path = {"month": None, "day": None, "borough": None, "zone": None}
    if "olap_revision" not in st.session_state:
        st.session_state.olap_revision = 0
    def navigate():
        # Returning to an earlier chart must not replay its previous selection.
        st.session_state.olap_revision += 1
        st.rerun()
    path = st.session_state.olap_path
    st.subheader("Explore pickup demand")
    st.caption("Click a bar to drill down.")
    labels = [f"Month {date.fromisoformat(path['month']):%m/%Y}" if path['month'] else "All months"]
    if path["day"]:
        labels.append(f"Day {date.fromisoformat(path['day']):%d/%m/%Y}")
    labels.append(path["borough"] or filters[2] or "All boroughs")
    if path["zone"]:
        labels.append(f"Zone #{path['zone']}")
    st.write(" → ".join(labels))
    if st.button("Reset exploration"):
        st.session_state.olap_filters = None
        navigate()

    scope = time_scope(filters, path["month"], path["day"])
    if path["borough"]:
        scope = (*scope[:2], path["borough"], scope[3], scope[4])
    if path["zone"]:
        scope = (*scope[:4], (int(path["zone"]),))
    level = "hour" if path["day"] else "day" if path["month"] else "month"
    time_rows, _ = _query(query, scope, level, "all")
    time_frame = _time_frame(time_rows, scope, level)
    st.metric("Pickups in current scope", f"{int(time_frame.trip_count.sum()):,}")
    time_title = {"month": "Month", "day": "Date", "hour": "Hour (New York)"}[level]
    time_heading, time_back = st.columns([4, 1])
    time_heading.subheader(f"By {time_title.lower()}")
    if time_back.button("← Back in time", disabled=not path["month"]):
        if path["day"]:
            path["day"] = None
        else:
            path["month"] = None
        navigate()
    event = st.altair_chart(pickup_chart(time_frame, "Time", time_title, selectable=level != "hour"),
        width="stretch", key=f"olap_time_{fingerprint}_{path}_{st.session_state.olap_revision}",
        on_select="rerun" if level != "hour" else "ignore")
    picked = _clicked(event) if level != "hour" else None
    # Keyboard-friendly alternative to clicking a bar, including zero-pickup days.
    if level != "hour":
        with st.form(f"drill_time_{level}"):
            lookup = dict(zip(time_frame.node, time_frame["Time"]))
            node = st.selectbox(f"Select {time_title.lower()}", list(lookup), format_func=lookup.get)
            if st.form_submit_button("Drill into time"):
                picked = node
    if picked in set(time_frame.node):
        path["month" if level == "month" else "day"] = picked
        navigate()

    geo_level = "zone" if path["borough"] else "borough"
    geography, _ = _query(query, scope, "all", geo_level)
    geo_heading, geo_back = st.columns([4, 1])
    geo_heading.subheader("Pickups by taxi zone" if geo_level == "zone" else "Pickups by borough")
    if geo_back.button("← Back to area", disabled=not path["borough"]):
        if path["zone"]:
            path["zone"] = None
        else:
            path["borough"] = None
        navigate()
    if not geography.empty and geography.trip_count.sum():
        if geo_level == "borough":
            geography["node"] = geography.borough
            geography["Area"] = geography.borough
        else:
            geography["node"] = geography.pickup_location_id.astype(str)
            geography["Area"] = geography.zone_name + " (#" + geography.node + ")"
        display = geography.nlargest(20, "trip_count")
        if len(geography) > 20:
            st.caption(f"Top 20 of {len(geography)} zones. Use the selector for all zones.")
        event = st.altair_chart(pickup_chart(display, "Area", "Area", horizontal=True, selectable=not path["zone"]),
            width="stretch", key=f"olap_geo_{fingerprint}_{path}_{st.session_state.olap_revision}",
            on_select="rerun" if not path["zone"] else "ignore")
        picked = _clicked(event) if not path["zone"] else None
        if not path["zone"]:
            with st.form(f"drill_geo_{geo_level}"):
                lookup = dict(zip(geography.node, geography["Area"]))
                node = st.selectbox("Select area", list(lookup), format_func=lookup.get)
                if st.form_submit_button("Drill into area"):
                    picked = node
        if picked in set(geography.node):
            path["borough" if geo_level == "borough" else "zone"] = picked
            navigate()
    else:
        st.info("No pickups in this scope. Go back to the previous level.")

    show_weekday_pattern(scope,query)

    if st.toggle("Show data table"):
        details, truncated = _query(query, scope, level, geo_level)
        st.dataframe(details, hide_index=True, width="stretch")
        st.download_button("Download CSV", details.to_csv(index=False).encode("utf-8-sig"),
                           "nyc_taxi_olap.csv", "text/csv")
        if not truncated and not details.empty:
            st.caption(f"Table total: {int(details.trip_count.sum()):,} pickups.")
