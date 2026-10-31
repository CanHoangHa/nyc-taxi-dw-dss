"""Applied filters and OLAP navigation keep a consistent analytical scope."""
from datetime import date
import unittest

from streamlit.testing.v1 import AppTest


class AnalyticsUITests(unittest.TestCase):
    def app(self):
        return AppTest.from_string('''
from datetime import date
from dashboard.analytics_controls import analytics_filters
zones = [dict(borough="Bronx", zone_name="A", pickup_location_id=1),
         dict(borough="Manhattan", zone_name="B", pickup_location_id=2)]
value = analytics_filters(date(2024,1,1), date(2024,4,30),
    [date(2024,m,1) for m in range(1,5)], ["Bronx","Manhattan"], zones)
import streamlit as st
st.session_state["applied_result"] = value
''').run()

    def test_edits_do_not_apply_until_submit(self):
        app = self.app()
        original = app.session_state["applied_result"]
        app.selectbox[0].select("Bronx").run()
        self.assertEqual(app.session_state["applied_result"], original)
        # A form only sends its draft widget values on submit (browser behavior).
        app.selectbox[0].select("Bronx")
        app.button[0].click().run()
        self.assertEqual(app.session_state["applied_result"][2], "Bronx")
        self.assertEqual(len(app.exception), 0)

    def test_invalid_date_preserves_last_applied_scope(self):
        app = self.app()
        original = app.session_state["applied_result"]
        app.date_input[0].set_value(date(2024,4,30))
        app.date_input[1].set_value(date(2024,1,1))
        app.button[0].click().run()
        self.assertEqual(app.session_state["applied_result"], original)
        self.assertTrue(len(app.error))

    def test_zone_outside_borough_is_not_silently_empty_data(self):
        app = self.app()
        app.selectbox[0].select("Bronx")
        app.multiselect[0].select("Manhattan · B (#2)")
        app.button[0].click().run()
        self.assertIsNone(app.session_state["applied_result"][2])
        self.assertTrue(len(app.error))

    def test_time_scope_clamps_to_original_filters(self):
        from dashboard.analytics_controls import time_scope
        original = (date(2024,1,15),date(2024,4,20),"Bronx",(6,9),(1,))
        self.assertEqual(time_scope(original, "2024-01-01", None),
                         (date(2024,1,15),date(2024,1,31),"Bronx",(6,9),(1,)))
        self.assertEqual(time_scope(original, "2024-04-01", "2024-04-19")[:2],
                         (date(2024,4,19),date(2024,4,19)))
        with self.assertRaises(ValueError):
            time_scope(original, "2024-01-01", "2024-02-02")

    def test_chart_navigation_and_rollup_preserve_totals_and_scope(self):
        app = AppTest.from_string('''
from datetime import date
from dashboard.olap_view import show_olap_explorer
import pandas as pd
import streamlit as st
frame=pd.DataFrame([dict(demand_date=date(2024,1,d),demand_hour=h,borough=b,
 pickup_location_id=z,zone_name=str(z),trip_count=d+h+z)
 for d in [1,2] for h in [8,9] for b,z in [("Bronx",1),("Manhattan",2)]])
def query(start,end,time,geo,borough,hours,zones,limit):
 f=frame.loc[frame.demand_date.between(start,end) & frame.demand_hour.between(*hours)].copy()
 if borough: f=f.loc[f.borough.eq(borough)]
 if zones: f=f.loc[f.pickup_location_id.isin(zones)]
 f["demand_month"]=pd.to_datetime(f.demand_date).dt.to_period("M").dt.to_timestamp()
 f["weekday"]=pd.to_datetime(f.demand_date).dt.dayofweek+1
 cols={"month":["demand_month"],"day":["demand_date"],"hour":["demand_hour"],"weekday_hour":["weekday","demand_hour"]}[time] if time!="all" else []
 cols+= {"all":[],"borough":["borough"],"zone":["borough","pickup_location_id","zone_name"]}[geo]
 return (f.groupby(cols,as_index=False).trip_count.sum().to_dict("records"),False)
show_olap_explorer((date(2024,1,1),date(2024,1,2),None,(8,9),()),query)
''').run()
        self.assertEqual(len(app.exception), 0)
        total = app.metric[0].value
        def click(label):
            next(button for button in app.button if button.label == label).click().run()
            self.assertEqual(len(app.exception), 0)
        click("Drill into time")
        self.assertEqual(app.metric[0].value, total)
        self.assertEqual(app.session_state["olap_path"]["month"], "2024-01-01")
        click("Drill into time")
        self.assertEqual(app.session_state["olap_path"]["day"], "2024-01-01")
        click("← Back in time")
        self.assertIsNone(app.session_state["olap_path"]["day"])
        self.assertEqual(app.metric[0].value, total)
        click("Drill into area")
        self.assertEqual(app.session_state["olap_path"]["borough"], "Bronx")
        click("Drill into area")
        self.assertEqual(app.session_state["olap_path"]["zone"], "1")
        click("Reset exploration")
        self.assertEqual(app.metric[0].value, total)

    def test_chart_click_payload_and_empty_time_cells(self):
        import pandas as pd
        from dashboard.olap_view import _clicked, _time_frame
        self.assertEqual(_clicked({"selection":{"drill":[{"node":"2024-01-01"}]}}),"2024-01-01")
        self.assertIsNone(_clicked({"selection":{"drill":[]}}))
        scope=(date(2024,1,1),date(2024,1,3),None,(8,9),())
        frame=_time_frame(pd.DataFrame([dict(demand_date=date(2024,1,2),trip_count=4)]),scope,"day")
        self.assertEqual(frame.trip_count.tolist(),[0,4,0])

    def test_horizontal_chart_keeps_every_zone_label(self):
        import pandas as pd
        from dashboard.olap_view import pickup_chart
        rows=pd.DataFrame({"zone":[f"Zone {n}" for n in range(30)],"trip_count":range(30)})
        spec=pickup_chart(rows,"zone","Taxi zone",horizontal=True).to_dict()
        bars = spec["layer"][0]
        self.assertFalse(bars["encoding"]["y"]["axis"]["labelOverlap"])
        self.assertEqual(spec["layer"][1]["encoding"]["text"]["field"], "trip_count")
        self.assertEqual(bars["encoding"]["x"]["scale"]["domain"][0], 0)
        self.assertGreaterEqual(spec["height"],30*len(rows))

    def test_missing_coverage_cannot_be_presented_as_zero(self):
        app=AppTest.from_string('''
from datetime import date
from dashboard.analytics_controls import analytics_filters
analytics_filters(date(2024,1,1),date(2024,3,31),
    [date(2024,1,1),date(2024,3,1)],[],[])
''').run()
        self.assertEqual(len(app.exception),0)
        self.assertTrue(any("02/2024" in item.value for item in app.error))

    def test_overview_average_includes_zero_pickup_calendar_days(self):
        app=AppTest.from_string('''
from datetime import date
from unittest.mock import patch
from dashboard.app import show_overview
data=({"trip_count":6,"active_zones":1,"active_days":2},
 [dict(demand_date=date(2024,1,1),trip_count=2),dict(demand_date=date(2024,1,3),trip_count=4)],
 [dict(demand_hour=8,trip_count=3),dict(demand_hour=9,trip_count=3)],
 [dict(borough="Bronx",trip_count=6)],
 [dict(zone_name="A",pickup_location_id=1,trip_count=6)])
with patch("dashboard.app.overview_data",return_value=data):
 show_overview((date(2024,1,1),date(2024,1,3),"Bronx",(8,9),(1,)))
''').run()
        self.assertEqual(len(app.exception),0)
        self.assertEqual([item.value for item in app.metric],["6","2.0","08:00"])

    def test_overview_can_show_thirty_zones_without_changing_filters(self):
        app=AppTest.from_string('''
from datetime import date
from unittest.mock import patch
from dashboard.app import show_overview
zones=[dict(zone_name=f"Zone {n}",pickup_location_id=n,trip_count=31-n) for n in range(1,31)]
data=({"trip_count":465},[dict(demand_date=date(2024,1,1),trip_count=465)],
      [dict(demand_hour=8,trip_count=465)],[dict(borough="Bronx",trip_count=465)],zones)
with patch("dashboard.app.overview_data",return_value=data):
 show_overview((date(2024,1,1),date(2024,1,1),"Bronx",(8,9),()))
''').run()
        self.assertEqual(app.selectbox[0].value,10)
        app.selectbox[0].select(30).run()
        self.assertEqual(len(app.exception),0)
        self.assertEqual(app.selectbox[0].value,30)
        self.assertEqual(app.metric[0].value,"465")


if __name__ == "__main__":
    unittest.main()
