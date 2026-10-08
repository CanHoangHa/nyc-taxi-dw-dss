{{ config(indexes=[{'columns': ['trip_source_key'], 'unique': true}]) }}

with trips as (
    select
        *,
        pickup_datetime::date as pickup_date,
        dropoff_datetime::date as dropoff_date,
        (
            extract(hour from pickup_datetime)::integer * 60
            + extract(minute from pickup_datetime)::integer + 1
        )::smallint as pickup_minute_key,
        (
            extract(hour from dropoff_datetime)::integer * 60
            + extract(minute from dropoff_datetime)::integer + 1
        )::smallint as dropoff_minute_key
    from {{ ref('stg_yellow_trip_valid') }}
)

select
    trip.trip_source_key,
    trip.batch_id,
    trip.source_dataset,
    trip.source_year,
    trip.source_month,
    trip.source_file,
    trip.source_file_sha256,
    trip.source_row_number,
    trip.ingested_at,
    pickup_date.date_key as pickup_date_key,
    dropoff_date.date_key as dropoff_date_key,
    pickup_time.time_key as pickup_time_key,
    dropoff_time.time_key as dropoff_time_key,
    pickup_zone.zone_key as pickup_zone_key,
    dropoff_zone.zone_key as dropoff_zone_key,
    case
        when trip.vendor_id is null then repeat('0', 32)
        else vendor.vendor_key
    end as vendor_key,
    case
        when trip.payment_type_id is null then repeat('0', 32)
        else payment.payment_type_key
    end as payment_type_key,
    trip.pickup_datetime,
    trip.dropoff_datetime,
    trip.pickup_location_id,
    trip.dropoff_location_id,
    trip.vendor_id,
    trip.payment_type_id,
    1::integer as trip_count,
    trip.passenger_count,
    trip.trip_distance,
    trip.trip_duration_minutes,
    trip.rate_code_id,
    trip.store_and_forward_flag,
    trip.fare_amount::numeric(12,2) as fare_amount,
    trip.extra_amount::numeric(12,2) as extra_amount,
    trip.mta_tax_amount::numeric(12,2) as mta_tax_amount,
    trip.tip_amount::numeric(12,2) as tip_amount,
    trip.tolls_amount::numeric(12,2) as tolls_amount,
    trip.improvement_surcharge_amount::numeric(12,2) as improvement_surcharge_amount,
    trip.total_amount::numeric(12,2) as total_amount,
    trip.congestion_surcharge_amount::numeric(12,2) as congestion_surcharge_amount,
    trip.airport_fee_amount::numeric(12,2) as airport_fee_amount
from trips as trip
left join {{ ref('dim_date') }} as pickup_date
    on trip.pickup_date = pickup_date.calendar_date
left join {{ ref('dim_date') }} as dropoff_date
    on trip.dropoff_date = dropoff_date.calendar_date
left join {{ ref('dim_time') }} as pickup_time
    on trip.pickup_minute_key = pickup_time.time_key
left join {{ ref('dim_time') }} as dropoff_time
    on trip.dropoff_minute_key = dropoff_time.time_key
left join {{ ref('dim_taxi_zone') }} as pickup_zone
    on trip.pickup_location_id = pickup_zone.location_id
left join {{ ref('dim_taxi_zone') }} as dropoff_zone
    on trip.dropoff_location_id = dropoff_zone.location_id
left join {{ ref('dim_vendor') }} as vendor
    on trip.vendor_id = vendor.vendor_id
left join {{ ref('dim_payment_type') }} as payment
    on trip.payment_type_id = payment.payment_type_id
