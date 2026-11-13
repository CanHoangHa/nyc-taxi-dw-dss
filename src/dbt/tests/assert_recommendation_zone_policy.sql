select
    zone_key,
    location_id,
    is_unknown,
    is_recommendation_eligible
from {{ ref('dim_taxi_zone') }}
where is_recommendation_eligible is distinct from (
    location_id between 1 and 263 and not is_unknown
)
    or (location_id in (264, 265) and is_recommendation_eligible)
    or (is_unknown and is_recommendation_eligible)

union all

select
    mart.pickup_zone_key,
    mart.pickup_location_id,
    zone.is_unknown,
    mart.is_recommendation_eligible
from {{ ref('mart_zone_hour_demand') }} as mart
join {{ ref('dim_taxi_zone') }} as zone
    on mart.pickup_zone_key = zone.zone_key
where mart.is_recommendation_eligible is distinct from zone.is_recommendation_eligible
    or zone.is_unknown
