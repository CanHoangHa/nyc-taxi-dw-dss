"""Small Gate B-compatible fixtures for DSS unit tests."""

from __future__ import annotations

import pandas as pd


def coverage_months(*months: int) -> pd.DataFrame:
    rows = []
    for month in months:
        start = pd.Timestamp(2024, month, 1)
        rows.append(
            {
                "source_year": 2024,
                "source_month": month,
                "coverage_start_date": start,
                "coverage_end_date": start + pd.offsets.MonthEnd(0),
                "valid_trip_count": 100,
            }
        )
    return pd.DataFrame(rows)


def eligible_zones() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "pickup_zone_key": "zone-1",
                "pickup_location_id": 1,
                "borough": "Manhattan",
                "zone_name": "Alpha",
                "is_recommendation_eligible": True,
            },
            {
                "pickup_zone_key": "zone-2",
                "pickup_location_id": 2,
                "borough": "Queens",
                "zone_name": "Beta",
                "is_recommendation_eligible": True,
            },
        ]
    )


def sparse_demand() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "demand_date": "2024-01-01",
                "demand_hour": 8,
                "pickup_zone_key": "zone-1",
                "pickup_location_id": 1,
                "borough": "Manhattan",
                "zone_name": "Alpha",
                "is_recommendation_eligible": True,
                "trip_count": 5,
            },
            {
                "demand_date": "2024-01-02",
                "demand_hour": 9,
                "pickup_zone_key": "zone-2",
                "pickup_location_id": 2,
                "borough": "Queens",
                "zone_name": "Beta",
                "is_recommendation_eligible": True,
                "trip_count": 7,
            },
            {
                "demand_date": "2024-01-01",
                "demand_hour": 10,
                "pickup_zone_key": "zone-264",
                "pickup_location_id": 264,
                "borough": "Unknown",
                "zone_name": "N/A",
                "is_recommendation_eligible": False,
                "trip_count": 11,
            },
        ]
    )
