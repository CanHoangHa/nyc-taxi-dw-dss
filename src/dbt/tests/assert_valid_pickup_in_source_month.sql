select trip_source_key
from {{ ref('stg_yellow_trip_valid') }}
where pickup_datetime < make_date(source_year, source_month, 1)
   or pickup_datetime >= (
       make_date(source_year, source_month, 1) + interval '1 month'
   )
