select trip_source_key
from {{ ref('stg_yellow_trip_valid') }}
where trip_distance::text in ('NaN', 'Infinity', '-Infinity')
   or fare_amount::text in ('NaN', 'Infinity', '-Infinity')
   or extra_amount::text in ('NaN', 'Infinity', '-Infinity')
   or mta_tax_amount::text in ('NaN', 'Infinity', '-Infinity')
   or tip_amount::text in ('NaN', 'Infinity', '-Infinity')
   or tolls_amount::text in ('NaN', 'Infinity', '-Infinity')
   or improvement_surcharge_amount::text in ('NaN', 'Infinity', '-Infinity')
   or total_amount::text in ('NaN', 'Infinity', '-Infinity')
   or congestion_surcharge_amount::text in ('NaN', 'Infinity', '-Infinity')
   or airport_fee_amount::text in ('NaN', 'Infinity', '-Infinity')
