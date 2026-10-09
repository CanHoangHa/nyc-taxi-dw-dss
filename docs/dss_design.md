# Planned DSS Design

No forecasting model or recommendation logic has been implemented yet.

## Forecast definition

- Horizon: day-ahead
- Grain: date × hour × pickup zone
- Target: `trip_count`
- Main input mart: `mart_zone_hour_demand`
- Coverage input: `mart_demand_coverage`; zero-fill only its listed months
- Publication: all 24 hours of day D after observations through 23:59 of D−1
- Eligible recommendation zones: TLC LocationIDs 1–263

At this publication time, safe observed-demand features include lags of 24,
48, and 168 hours, rolling statistics shifted by at least 24 hours, and
calendar features known before day D. Same-day `lag_1` for hours 01–23 would
use information unavailable at issuance. Person 3 owns dense-grid generation,
feature engineering, model evaluation, and recommendations.

## Expected output

For a future zone-hour combination, the DSS is expected to present:

- Taxi zone and hourly period
- Predicted pickup demand
- Relevant historical demand baseline
- Interpretable demand level
- Recommendation about whether taxi availability should be prioritized

Exact model features, algorithms, evaluation split, metrics, demand-level
thresholds, and recommendation wording remain TBD.

## Prediction versus recommendation

A prediction estimates `trip_count`. It is not by itself a decision-support
result. The DSS must compare the prediction with context such as historical
demand and convert it into an understandable demand level and actionable
recommendation. Forecasting and recommendation logic will remain separate
components.
