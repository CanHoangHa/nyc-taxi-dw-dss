# Planned Data Contracts

These contracts describe interfaces and ownership only. They are not final
schemas, and no corresponding database objects exist yet.

## `raw.yellow_trip`

- Producer: Python ingestion
- Consumer: dbt staging
- Planned grain: one source Parquet row
- Purpose: preserve Yellow Taxi source data with minimal transformation and
  ingestion lineage
- Planned metadata: batch, source file, checksum, source month, source row, and
  ingestion timestamp
- Exact columns and database types: TBD

## `stg_yellow_trip`

- Producer: dbt staging
- Consumers: dbt dimensions and facts
- Planned grain: one normalized raw trip record
- Purpose: provide canonical names and types, derived fields, and a documented
  data-quality classification
- Planned states: valid, quarantined, rejected
- Detailed validation rules and thresholds: TBD

## `fact_trip`

- Producer: dbt warehouse models
- Consumers: analytical marts and OLAP queries
- Planned grain: one valid Yellow Taxi trip
- Planned relationships: date, time, taxi zone, vendor, and payment type
  dimensions
- Planned measures: passenger, distance, duration, fare, tip, toll, and total
  amount measures
- Final foreign keys and measure list: TBD

## `mart_zone_hour_demand`

- Producer: dbt mart models
- Consumers: DSS feature preparation and dashboard
- Planned grain: date × hour × pickup zone
- Required target metric: `trip_count`
- Planned descriptive attributes: zone and calendar context
- Lag, rolling, baseline, and model feature fields: TBD
