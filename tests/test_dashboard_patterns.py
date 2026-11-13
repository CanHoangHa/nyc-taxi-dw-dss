"""Historical averages and forecast patterns have different meanings."""
from datetime import date
import unittest

import pandas as pd


class DashboardPatternTests(unittest.TestCase):
    def test_weekday_average_includes_zero_pickup_days(self):
        from dashboard.pattern_charts import weekday_hour_grid
        # Two Mondays, only one has pickups; the second still enters the divisor.
        rows=[dict(weekday=1,demand_hour=8,trip_count=20)]
        grid=weekday_hour_grid(rows,date(2024,1,1),date(2024,1,8),(8,9))
        monday=grid.loc[grid.weekday.eq(1)]
        self.assertEqual(monday.average_pickups.tolist(),[10,0])
        self.assertEqual(monday.days.tolist(),[2,2])
        self.assertEqual(len(grid),14)

    def test_weekday_not_in_date_range_is_unavailable_not_zero(self):
        from dashboard.pattern_charts import weekday_hour_grid
        grid=weekday_hour_grid([],date(2024,1,1),date(2024,1,1),(0,23))
        self.assertEqual(len(grid),168)
        self.assertTrue(grid.loc[grid.weekday.eq(1)].average_pickups.eq(0).all())
        self.assertTrue(grid.loc[grid.weekday.eq(2)].average_pickups.isna().all())

    def test_forecast_top_zones_are_chosen_by_prediction_not_baseline(self):
        from dashboard.pattern_charts import forecast_zone_comparison, forecast_zone_grid
        ranking=pd.DataFrame([dict(pickup_location_id=n,zone_name=str(n),
            predicted_trip_count=100-n,baseline_trip_count=n*10) for n in range(1,13)])
        comparison=forecast_zone_comparison(ranking,k=10)
        self.assertEqual(set(comparison.pickup_location_id),set(range(1,11)))
        self.assertEqual(len(comparison),20)
        self.assertEqual(comparison.loc[comparison.series.eq("Forecast"),"pickups"].sum(),945)
        hourly=pd.DataFrame([dict(pickup_location_id=n,demand_hour=h,predicted_trip_count=n+h)
            for n in range(1,13) for h in [8,9]])
        grid=forecast_zone_grid(ranking,hourly,start=8,end=10,k=10)
        self.assertEqual(len(grid),20)
        self.assertEqual(set(grid.demand_hour),{8,9})
        with self.assertRaisesRegex(ValueError,"complete"):
            forecast_zone_grid(ranking,hourly.iloc[1:],start=8,end=10,k=10)


if __name__ == "__main__":
    unittest.main()
