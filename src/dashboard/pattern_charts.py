"""Small chart datasets: historical calendar averages and fixed forecast ranks."""
import altair as alt
import pandas as pd
import streamlit as st
from dashboard.appearance import chart_palette, show_chart


WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def weekday_hour_grid(rows, start, end, hours):
    calendar = pd.date_range(start, end)
    counts = pd.Series(calendar.dayofweek + 1).value_counts()
    index = pd.MultiIndex.from_product([range(1,8), range(hours[0],hours[1]+1)],
                                      names=["weekday","demand_hour"])
    values = pd.DataFrame(rows, columns=["weekday","demand_hour","trip_count"])
    if values.duplicated(["weekday","demand_hour"]).any():
        raise ValueError("weekday/hour totals must be unique")
    grid = values.set_index(["weekday","demand_hour"]).reindex(index,fill_value=0).reset_index()
    grid["days"] = grid.weekday.map(counts).fillna(0).astype(int)
    grid["average_pickups"] = grid.trip_count / grid.days.where(grid.days.gt(0))
    grid["weekday_label"] = grid.weekday.map(dict(enumerate(WEEKDAYS,1)))
    return grid


def _top_zones(ranking, k):
    top = ranking.sort_values(["predicted_trip_count","pickup_location_id"],ascending=[False,True]).head(k).copy()
    top["zone_label"] = top.zone_name + " (#" + top.pickup_location_id.astype(str) + ")"
    return top


def forecast_zone_comparison(ranking, k=10):
    top = _top_zones(ranking,k)
    result = top.melt(id_vars=["pickup_location_id","zone_label"],
        value_vars=["predicted_trip_count","baseline_trip_count"],var_name="series",value_name="pickups")
    result["series"] = result.series.map({"predicted_trip_count":"Forecast","baseline_trip_count":"Last week (D−7)"})
    return result


def forecast_zone_grid(ranking, hourly, *, start, end, k=10):
    top = _top_zones(ranking,k)
    selected = hourly.loc[hourly.pickup_location_id.isin(top.pickup_location_id)
                          & hourly.demand_hour.ge(start) & hourly.demand_hour.lt(end)].copy()
    expected = pd.MultiIndex.from_product([top.pickup_location_id,range(start,end)],
                                         names=["pickup_location_id","demand_hour"])
    actual = pd.MultiIndex.from_frame(selected[list(expected.names)])
    if actual.has_duplicates or len(actual)!=len(expected) or not expected.isin(actual).all():
        raise ValueError("forecast heatmap requires complete zone-hour coverage")
    return selected.merge(top[["pickup_location_id","zone_label"]],on="pickup_location_id",validate="many_to_one")


def weekday_heatmap(grid):
    base = alt.Chart(grid).encode(
        x=alt.X("demand_hour:O",title="Hour (New York)",sort="ascending",axis=alt.Axis(labelAngle=0)),
        y=alt.Y("weekday_label:N",title=None,sort=WEEKDAYS),
        tooltip=[alt.Tooltip("weekday_label:N",title="Weekday"),alt.Tooltip("demand_hour:O",title="Hour"),
                 alt.Tooltip("average_pickups:Q",title="Avg. pickups/day",format=",.1f"),
                 alt.Tooltip("days:Q",title="Matching dates",format="d")],
    )
    missing_color = "#d1d5db"
    background = base.mark_rect(color=missing_color,strokeWidth=1,stroke="#64748b")
    cells = base.mark_rect(strokeWidth=1,stroke="#64748b").transform_filter(
        "isValid(datum.average_pickups)").encode(color=alt.Color("average_pickups:Q",
            title="Avg. pickups/day",scale=alt.Scale(scheme="blues",domainMin=0)))
    return (background + cells).properties(height=280)


def show_weekday_pattern(filters, query):
    start,end,borough,hours,zones = filters
    rows,truncated = query(start,end,"weekday_hour","all",borough,hours,zones,5000)
    if truncated:
        raise ValueError("weekday/hour query unexpectedly exceeded 168 cells")
    grid = weekday_hour_grid(rows,start,end,hours)
    st.subheader("Average pickups by weekday and hour")
    st.caption(f"{start:%d %b %Y}–{end:%d %b %Y} · Each cell averages all occurrences of that weekday. "
               "Days with no pickups count as zero; grey means the weekday is outside the date range.")
    show_chart(weekday_heatmap(grid),width="stretch")


def show_forecast_patterns(ranking, hourly, start, end, k=10):
    comparison = forecast_zone_comparison(ranking,k=k)
    order = comparison.zone_label.drop_duplicates().tolist()
    st.subheader("Top zones: forecast vs. last week")
    chart = alt.Chart(comparison).mark_bar().encode(
        x=alt.X("pickups:Q",title="Pickups",scale=alt.Scale(zero=True)),
        y=alt.Y("zone_label:N",title=None,sort=order,axis=alt.Axis(labelOverlap=False,labelLimit=280)),
        yOffset=alt.YOffset("series:N",sort=["Forecast","Last week (D−7)"]),
        color=alt.Color("series:N",title=None,scale=alt.Scale(
            domain=["Forecast","Last week (D−7)"],range=list(chart_palette())),legend=alt.Legend(orient="top")),
        tooltip=[alt.Tooltip("zone_label:N",title="Taxi zone"),alt.Tooltip("series:N",title="Series"),
                 alt.Tooltip("pickups:Q",title="Pickups",format=",.1f")],
    ).properties(height=max(180,44*len(order)))
    show_chart(chart,width="stretch")
    with st.expander("Hourly pattern by zone"):
        if end-start==1:
            st.caption("Select more than one hour to compare patterns across the interval.")
        else:
            grid = forecast_zone_grid(ranking,hourly,start=start,end=end,k=k)
            heatmap = alt.Chart(grid).mark_rect(stroke="#64748b",strokeWidth=1).encode(
                x=alt.X("demand_hour:O",title="Hour (New York)",sort="ascending",axis=alt.Axis(labelAngle=0)),
                y=alt.Y("zone_label:N",title=None,sort=order,axis=alt.Axis(labelOverlap=False,labelLimit=280)),
                color=alt.Color("predicted_trip_count:Q",title="Forecast pickups",scale=alt.Scale(scheme="blues",domainMin=0)),
                tooltip=[alt.Tooltip("zone_label:N",title="Taxi zone"),alt.Tooltip("demand_hour:O",title="Hour"),
                         alt.Tooltip("predicted_trip_count:Q",title="Forecast pickups",format=",.1f")],
            ).properties(height=max(150,32*len(order)))
            show_chart(heatmap,width="stretch")
