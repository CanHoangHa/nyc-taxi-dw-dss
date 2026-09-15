# Approved Design Decisions

The following decisions are frozen for the initial project scope:

| Area | Approved decision |
|---|---|
| Dataset | NYC TLC Yellow Taxi Trip Records for 2024 |
| Source organization | Monthly Parquet files |
| Reference data | NYC Taxi Zone Lookup |
| Batch grain | One source month per ingestion batch |
| Fact grain | One valid Yellow Taxi trip per `fact_trip` row |
| Forecast horizon | Day-ahead |
| Forecast grain | Date × hour × pickup zone |
| Forecast target | `trip_count` |
| Airflow responsibility | Orchestration only |
| Main DSS mart | `mart_zone_hour_demand` |
| Zone modeling | One role-playing `dim_taxi_zone` for pickup and drop-off |
| Data-quality states | Valid, quarantined, and rejected |

Exact schemas, data-quality thresholds, model choice, forecast thresholds,
infrastructure configuration, and dashboard layout remain intentionally TBD.
