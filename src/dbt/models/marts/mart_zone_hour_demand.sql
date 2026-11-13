{{ config(indexes=[{
    'columns': ['demand_date', 'demand_hour', 'pickup_zone_key'],
    'unique': true
}]) }}

select
    date_dim.calendar_date as demand_date,
    time_dim.hour_of_day as demand_hour,
    fact.pickup_zone_key,
    zone.location_id as pickup_location_id,
    zone.borough,
    zone.zone_name,
    zone.is_recommendation_eligible,
    sum(fact.trip_count)::bigint as trip_count
from {{ ref('fact_trip') }} as fact
join {{ ref('dim_date') }} as date_dim
    on fact.pickup_date_key = date_dim.date_key
join {{ ref('dim_time') }} as time_dim
    on fact.pickup_time_key = time_dim.time_key
join {{ ref('dim_taxi_zone') }} as zone
    on fact.pickup_zone_key = zone.zone_key
group by
    date_dim.calendar_date,
    time_dim.hour_of_day,
    fact.pickup_zone_key,
    zone.location_id,
    zone.borough,
    zone.zone_name,
    zone.is_recommendation_eligible
