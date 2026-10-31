"""Commit a planning scope only after the user finishes choosing inputs."""
import streamlit as st


def planning_scope(dates, zone_reference):
    zones = zone_reference.loc[zone_reference.is_actionable & zone_reference.pickup_location_id.between(1,263)]
    boroughs = sorted(zones.borough.unique().tolist())
    if not boroughs:
        st.info("No eligible zones available.")
        st.stop()
    default = (dates[0], "Manhattan" if "Manhattan" in boroughs else boroughs[0], (6,10), (), 10)
    if ("planning_applied" not in st.session_state
            or st.session_state.planning_applied[0] not in dates):
        st.session_state.planning_applied = default
    applied = st.session_state.planning_applied
    with st.sidebar:
        st.header("Planning scope")
        with st.form("planning_scope"):
            day = st.selectbox("Forecast date",dates,index=dates.index(applied[0]),
                format_func=lambda value:value.strftime("%d/%m/%Y"),key="planning_date")
            borough = st.selectbox("Borough",boroughs,index=boroughs.index(applied[1]),key="planning_borough")
            hours = st.slider("Shift hours [start, end)",0,24,applied[2],key="planning_hours",
                              help="End excluded: [6,10) means 06:00–09:59, New York time.")
            options = {f"{z.borough} · {z.zone_name} (#{z.pickup_location_id})":z
                       for z in zones.sort_values(["borough","zone_name"]).itertuples(index=False)}
            chosen = st.multiselect("Taxi zones (optional)",list(options),
                default=[label for label,zone in options.items() if zone.pickup_location_id in applied[3]],key="planning_zones",
                help="Leave empty for all zones in the borough. Chosen zones must belong to that borough.")
            limit = st.selectbox("Zones to review",[5,10,20],index=[5,10,20].index(applied[4]),key="planning_limit",
                                help="Maximum number of zones to list; this does not specify a taxi fleet size.")
            if st.form_submit_button("Apply",type="primary"):
                if hours[0]>=hours[1]:
                    st.error("Select at least one hour. Previous scope retained.")
                elif any(options[item].borough!=borough for item in chosen):
                    st.error("Choose zones in the selected borough. Previous scope retained.")
                else:
                    st.session_state.planning_applied = (day,borough,tuple(hours),
                        tuple(sorted(int(options[item].pickup_location_id) for item in chosen)),limit)
        if st.button("Reload forecasts"):
            st.rerun()
    return st.session_state.planning_applied
