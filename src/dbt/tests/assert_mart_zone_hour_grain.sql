select
    demand_date,
    demand_hour,
    pickup_zone_key,
    count(*) as row_count
from {{ ref('mart_zone_hour_demand') }}
group by demand_date, demand_hour, pickup_zone_key
having count(*) != 1
    or min(demand_hour) not between 0 and 23
    or min(trip_count) <= 0
