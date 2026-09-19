{{ config(materialized='table') }}

with normalized as (
    select
        md5(concat_ws(
            '|',
            source_dataset,
            source_year::text,
            source_month::text,
            source_row_number::text
        )) as trip_source_key,
        batch_id,
        source_dataset,
        source_year,
        source_month,
        source_file,
        source_file_sha256,
        source_row_number,
        ingested_at,
        make_date(source_year, source_month, 1) as source_month_start,
        "VendorID"::smallint as vendor_id,
        "tpep_pickup_datetime" as pickup_datetime,
        "tpep_dropoff_datetime" as dropoff_datetime,
        "passenger_count"::smallint as passenger_count,
        "trip_distance" as trip_distance,
        "RatecodeID"::smallint as rate_code_id,
        case upper(trim("store_and_fwd_flag"))
            when 'Y' then 'Y'
            when 'N' then 'N'
        end as store_and_forward_flag,
        "PULocationID" as pickup_location_id,
        "DOLocationID" as dropoff_location_id,
        "payment_type"::smallint as payment_type_id,
        "fare_amount"::numeric(12, 2) as fare_amount,
        "extra"::numeric(12, 2) as extra_amount,
        "mta_tax"::numeric(12, 2) as mta_tax_amount,
        "tip_amount"::numeric(12, 2) as tip_amount,
        "tolls_amount"::numeric(12, 2) as tolls_amount,
        "improvement_surcharge"::numeric(12, 2) as improvement_surcharge_amount,
        "total_amount"::numeric(12, 2) as total_amount,
        "congestion_surcharge"::numeric(12, 2) as congestion_surcharge_amount,
        "Airport_fee"::numeric(12, 2) as airport_fee_amount,
        (
            extract(epoch from (
                "tpep_dropoff_datetime" - "tpep_pickup_datetime"
            )) / 60.0
        )::double precision as trip_duration_minutes,
        pickup_zone.location_id is not null as pickup_zone_exists,
        dropoff_zone.location_id is not null as dropoff_zone_exists
    from {{ source('raw', 'yellow_trip') }} as trip
    left join {{ ref('taxi_zone_lookup') }} as pickup_zone
        on trip."PULocationID" = pickup_zone.location_id
    left join {{ ref('taxi_zone_lookup') }} as dropoff_zone
        on trip."DOLocationID" = dropoff_zone.location_id
),

classified as (
    select
        *,
        array_remove(array[
            case when pickup_datetime is null then 'MISSING_PICKUP_DATETIME' end,
            case when dropoff_datetime is null then 'MISSING_DROPOFF_DATETIME' end,
            case when dropoff_datetime < pickup_datetime then 'DROPOFF_BEFORE_PICKUP' end,
            case when
                pickup_datetime < source_month_start
                or pickup_datetime >= source_month_start + interval '1 month'
                then 'PICKUP_OUTSIDE_SOURCE_MONTH'
            end,
            case when not pickup_zone_exists then 'UNKNOWN_PICKUP_ZONE' end,
            case when not dropoff_zone_exists then 'UNKNOWN_DROPOFF_ZONE' end,
            case when trip_distance < 0 then 'NEGATIVE_TRIP_DISTANCE' end,
            case when trip_duration_minutes <= 0 then 'NON_POSITIVE_DURATION' end,
            case when trip_duration_minutes > 180 then 'EXCESSIVE_DURATION' end,
            case when
                fare_amount < 0
                or extra_amount < 0
                or mta_tax_amount < 0
                or tip_amount < 0
                or tolls_amount < 0
                or improvement_surcharge_amount < 0
                or total_amount < 0
                or congestion_surcharge_amount < 0
                or airport_fee_amount < 0
                then 'NEGATIVE_MONETARY_VALUE'
            end
        ]::text[], null) as dq_reason_codes
    from normalized
)

select
    trip_source_key,
    batch_id,
    source_dataset,
    source_year,
    source_month,
    source_file,
    source_file_sha256,
    source_row_number,
    ingested_at,
    vendor_id,
    pickup_datetime,
    dropoff_datetime,
    passenger_count,
    trip_distance,
    rate_code_id,
    store_and_forward_flag,
    pickup_location_id,
    dropoff_location_id,
    payment_type_id,
    fare_amount,
    extra_amount,
    mta_tax_amount,
    tip_amount,
    tolls_amount,
    improvement_surcharge_amount,
    total_amount,
    congestion_surcharge_amount,
    airport_fee_amount,
    trip_duration_minutes,
    case
        when dq_reason_codes && array[
            'MISSING_PICKUP_DATETIME',
            'MISSING_DROPOFF_DATETIME',
            'DROPOFF_BEFORE_PICKUP'
        ]::text[] then 'rejected'
        when cardinality(dq_reason_codes) > 0 then 'quarantined'
        else 'valid'
    end as dq_status,
    dq_reason_codes
from classified
