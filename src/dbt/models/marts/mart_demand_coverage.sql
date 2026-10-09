{{ config(materialized='view') }}

-- A month is safe to zero-fill only after classified ingestion, fact build,
-- and demand-mart build all agree on its valid-trip total. A view rechecks
-- these counts when the consumer queries it, including after a new load.
with classified_months as (
    select
        source_year,
        source_month,
        sum(valid_count)::bigint as valid_trip_count
    from {{ source('audit', 'etl_batch') }}
    where dataset_name = 'yellow_taxi'
        and status = 'succeeded'
    group by source_year, source_month
    having count(*) = count(valid_count)
),
fact_months as (
    select
        source_year,
        source_month,
        sum(trip_count)::bigint as trip_count
    from {{ ref('fact_trip') }}
    group by source_year, source_month
),
mart_months as (
    select
        extract(year from demand_date)::smallint as source_year,
        extract(month from demand_date)::smallint as source_month,
        sum(trip_count)::bigint as trip_count
    from {{ ref('mart_zone_hour_demand') }}
    group by 1, 2
)
select
    classified.source_year,
    classified.source_month,
    make_date(classified.source_year, classified.source_month, 1) as coverage_start_date,
    (
        make_date(classified.source_year, classified.source_month, 1)
        + interval '1 month' - interval '1 day'
    )::date as coverage_end_date,
    classified.valid_trip_count
from classified_months as classified
left join fact_months as fact
    on classified.source_year = fact.source_year
    and classified.source_month = fact.source_month
left join mart_months as mart
    on classified.source_year = mart.source_year
    and classified.source_month = mart.source_month
where classified.valid_trip_count = coalesce(fact.trip_count, 0)
    and classified.valid_trip_count = coalesce(mart.trip_count, 0)
