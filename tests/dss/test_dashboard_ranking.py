"""Exercise actual Streamlit widgets/rendering using the AppTest harness."""
import unittest

from streamlit.testing.v1 import AppTest


class DashboardRankingTests(unittest.TestCase):
    def test_refit_metadata_and_selection_metrics_are_labelled_separately(self):
        app = AppTest.from_string('''
from datetime import date
from unittest.mock import patch
from dashboard.app import show_dss
from tests.dss.test_forest_ranking import forecasts, zone_reference
run = dict(model_name="random_forest", model_version="1", feature_version="1",
 recommendation_version="1", run_id="refit-run", fit_kind="refit",
 train_start_date=date(2024,1,29), train_end_date=date(2024,2,29),
 validation_start_date=date(2024,3,1), validation_end_date=date(2024,3,15),
 fit_start_date=date(2024,1,29), fit_end_date=date(2024,3,31), fit_seconds=337.5229522)
rows=forecasts()
rows["demand_ratio"]=1.0
rows["recommendation"]="label"
rows["recommendation_reason"]="reason"
with patch("dashboard.app.DssService.available_forecast_dates", return_value=[date(2024,4,30)]), \\
     patch("dashboard.app.dss_forecasts", return_value=(run, rows, {"selection_validation":{"random_forest":{"wape":0.1772}}}, zone_reference())):
    show_dss()
''', default_timeout=30).run()
        self.assertEqual(len(app.exception), 0)
        captions = " ".join(item.value for item in app.caption)
        self.assertIn("31/03/2024", captions)
        self.assertIn("337.52", captions)
        self.assertIn("29/02/2024", captions)
        self.assertIn("15/03/2024", captions)
        self.assertTrue(any("selection" in item.label for item in app.expander))
        self.assertTrue(any("April 2024" in item.label for item in app.expander))
        self.assertTrue(any("history through 29 Apr 2024" in item.value for item in app.info))
        self.assertTrue(any(item.label == "Model details" for item in app.expander))
        self.assertNotIn("ranking_reason", app.dataframe[0].value.columns)
        self.assertNotIn("hour_count", app.dataframe[0].value.columns)
        self.assertNotIn("recommendation_reason", app.dataframe[1].value.columns)
        self.assertNotIn("created_at", captions)

    def test_borough_interval_totals_details_and_invalid_range(self):
        app = AppTest.from_string('''
from datetime import date
import streamlit as st
from unittest.mock import patch
from dashboard.app import show_dss
from tests.dss.test_forest_ranking import forecasts, zone_reference
run = dict(model_name="random_forest", model_version="1.0.0",
           feature_version="1.0.0", recommendation_version="1.2.0", run_id="test")
rows = forecasts()
if st.session_state.get("drop_zone", False):
    rows = rows.loc[rows.pickup_location_id.ne(2)]
rows["demand_ratio"] = 1.0
rows["recommendation"] = "hourly label"
rows["recommendation_reason"] = "hourly explanation"
with patch("dashboard.app.DssService.available_forecast_dates", return_value=[date(2024,3,16)]), \\
     patch("dashboard.app.dss_forecasts", return_value=(run, rows, {}, zone_reference())):
    show_dss()
''', default_timeout=30).run()
        self.assertEqual(len(app.exception), 0)
        original = app.dataframe[0].value
        app.selectbox[1].select("Queens").run()
        self.assertEqual(app.dataframe[0].value.pickup_location_id.tolist(), original.pickup_location_id.tolist())
        app.selectbox[1].select("Queens")
        next(button for button in app.button if button.label == "Apply").click().run()
        self.assertEqual(len(app.exception), 0)
        ranking = app.dataframe[0].value
        self.assertEqual(ranking.pickup_location_id.tolist(), [1, 2, 3])
        self.assertEqual(ranking.predicted_trip_count.tolist(), [16, 16, 0])
        self.assertEqual(len(app.dataframe[1].value), 12)
        app.session_state["drop_zone"] = True
        app.run()
        self.assertEqual(len(app.exception), 0)
        self.assertIn("missing forecast", app.warning[0].value)
        self.assertEqual(len(app.dataframe), 0)
        app.session_state["drop_zone"] = False
        app.slider[0].set_range(10, 10)
        next(button for button in app.button if button.label == "Apply").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.error), 1)
        self.assertEqual(app.dataframe[0].value.pickup_location_id.tolist(), [1,2,3])

    def test_shortlist_limit_and_planning_scope_apply_together(self):
        app=AppTest.from_string('''
from datetime import date
import pandas as pd
from unittest.mock import patch
from dashboard.app import show_dss
from tests.dss.test_forest_ranking import forecasts
pieces=[]
for zone in range(10,22):
 f=forecasts().loc[lambda f:f.pickup_location_id.eq(1)].copy()
 f["pickup_location_id"]=zone
 f["pickup_zone_key"]=str(zone)
 f["zone_name"]=f"Zone {zone}"
 f["demand_ratio"]=1.0
 pieces.append(f)
rows=pd.concat(pieces,ignore_index=True)
reference=rows[["pickup_location_id","borough","zone_name","is_actionable"]].drop_duplicates()
run=dict(model_name="random_forest",model_version="1",feature_version="1",recommendation_version="1",run_id="test")
with patch("dashboard.app.DssService.available_forecast_dates",return_value=[date(2024,3,16)]), \\
 patch("dashboard.app.dss_forecasts",return_value=(run,rows,{},reference)):
 show_dss()
''').run()
        self.assertEqual(len(app.exception),0)
        original_total=app.metric[0].value
        self.assertEqual(len(app.dataframe[0].value),10)
        app.selectbox[2].select(5)
        next(button for button in app.button if button.label=="Apply").click().run()
        self.assertEqual(len(app.exception),0)
        self.assertEqual(len(app.dataframe[0].value),5)
        self.assertEqual(app.metric[0].value,original_total)
        headings=[item.value for item in app.subheader]
        self.assertLess(headings.index("Zones to review"),headings.index("Hourly forecast vs. last week"))


if __name__ == "__main__":
    unittest.main()
