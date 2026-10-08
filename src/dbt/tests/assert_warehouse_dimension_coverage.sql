with source_zones as (
    select pickup_location_id as location_id from {{ ref('stg_yellow_trip_valid') }}
    union
    select dropoff_location_id from {{ ref('stg_yellow_trip_valid') }}
),
source_dates as (
    select pickup_datetime::date as calendar_date from {{ ref('stg_yellow_trip_valid') }}
    union
    select dropoff_datetime::date from {{ ref('stg_yellow_trip_valid') }}
),
source_times as (
    select (
        extract(hour from pickup_datetime)::integer * 60
        + extract(minute from pickup_datetime)::integer + 1
    )::smallint as time_key from {{ ref('stg_yellow_trip_valid') }}
    union
    select (
        extract(hour from dropoff_datetime)::integer * 60
        + extract(minute from dropoff_datetime)::integer + 1
    )::smallint from {{ ref('stg_yellow_trip_valid') }}
),
source_vendors as (
    select distinct vendor_id
    from {{ ref('stg_yellow_trip_valid') }}
    where vendor_id is not null
),
source_payments as (
    select distinct payment_type_id
    from {{ ref('stg_yellow_trip_valid') }}
    where payment_type_id is not null
),
missing as (
    select 'zone' as dimension_name, location_id::text as business_key
    from (select location_id from source_zones
          except select location_id from {{ ref('dim_taxi_zone') }}) as gap
    union all
    select 'date', calendar_date::text
    from (select calendar_date from source_dates
          except select calendar_date from {{ ref('dim_date') }}) as gap
    union all
    select 'time', time_key::text
    from (select time_key from source_times
          except select time_key from {{ ref('dim_time') }}) as gap
    union all
    select 'vendor', vendor_id::text
    from (select vendor_id from source_vendors
          except select vendor_id from {{ ref('dim_vendor') }}) as gap
    union all
    select 'payment_type', payment_type_id::text
    from (select payment_type_id from source_payments
          except select payment_type_id from {{ ref('dim_payment_type') }}) as gap
)

select * from missing
