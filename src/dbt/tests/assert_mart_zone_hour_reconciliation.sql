with expected as (
    select
        pickup_datetime::date as demand_date,
        extract(hour from pickup_datetime)::smallint as demand_hour,
        pickup_zone_key,
        pickup_location_id,
        count(*) as trip_count
    from {{ ref('fact_trip') }}
    group by
        pickup_datetime::date,
        extract(hour from pickup_datetime)::smallint,
        pickup_zone_key,
        pickup_location_id
)

select
    coalesce(expected.demand_date, observed.demand_date) as demand_date,
    coalesce(expected.demand_hour, observed.demand_hour) as demand_hour,
    coalesce(expected.pickup_zone_key, observed.pickup_zone_key) as pickup_zone_key,
    expected.trip_count as expected_trips,
    observed.trip_count as mart_trips
from expected
full join {{ ref('mart_zone_hour_demand') }} as observed
    on expected.demand_date = observed.demand_date
    and expected.demand_hour = observed.demand_hour
    and expected.pickup_zone_key = observed.pickup_zone_key
    and expected.pickup_location_id = observed.pickup_location_id
where expected.trip_count is distinct from observed.trip_count
