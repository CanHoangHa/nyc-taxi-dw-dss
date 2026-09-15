# Planned DSS Design

No forecasting model or recommendation logic has been implemented yet.

## Forecast definition

- Horizon: day-ahead
- Grain: date × hour × pickup zone
- Target: `trip_count`
- Main input mart: `mart_zone_hour_demand`

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
