{{ config(materialized='table') }}

with source_rows as (
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
        "VendorID" as vendor_id_raw,
        "tpep_pickup_datetime" as pickup_datetime,
        "tpep_dropoff_datetime" as dropoff_datetime,
        "passenger_count" as passenger_count_raw,
        "trip_distance" as trip_distance_raw,
        "RatecodeID" as rate_code_id_raw,
        "store_and_fwd_flag" as store_and_forward_flag_raw,
        "PULocationID" as pickup_location_id,
        "DOLocationID" as dropoff_location_id,
        "payment_type" as payment_type_id_raw,
        "fare_amount" as fare_amount_raw,
        "extra" as extra_amount_raw,
        "mta_tax" as mta_tax_amount_raw,
        "tip_amount" as tip_amount_raw,
        "tolls_amount" as tolls_amount_raw,
        "improvement_surcharge" as improvement_surcharge_amount_raw,
        "total_amount" as total_amount_raw,
        "congestion_surcharge" as congestion_surcharge_amount_raw,
        "Airport_fee" as airport_fee_amount_raw,
        pickup_zone.location_id is not null as pickup_zone_exists,
        dropoff_zone.location_id is not null as dropoff_zone_exists
    from {{ source('raw', 'yellow_trip') }} as trip
    left join {{ ref('taxi_zone_lookup') }} as pickup_zone
        on trip."PULocationID" = pickup_zone.location_id
    left join {{ ref('taxi_zone_lookup') }} as dropoff_zone
        on trip."DOLocationID" = dropoff_zone.location_id
),

quality_flags as (
    select
        *,
        (
            (
                vendor_id_raw is not null
                and vendor_id_raw not between -32768 and 32767
            )
            or (
                passenger_count_raw is not null
                and passenger_count_raw not between -32768 and 32767
            )
            or (
                rate_code_id_raw is not null
                and rate_code_id_raw not between -32768 and 32767
            )
            or (
                payment_type_id_raw is not null
                and payment_type_id_raw not between -32768 and 32767
            )
            or (
                fare_amount_raw is not null
                and not {{ is_non_finite_float('fare_amount_raw') }}
                and not {{ fits_numeric_12_2('fare_amount_raw') }}
            )
            or (
                extra_amount_raw is not null
                and not {{ is_non_finite_float('extra_amount_raw') }}
                and not {{ fits_numeric_12_2('extra_amount_raw') }}
            )
            or (
                mta_tax_amount_raw is not null
                and not {{ is_non_finite_float('mta_tax_amount_raw') }}
                and not {{ fits_numeric_12_2('mta_tax_amount_raw') }}
            )
            or (
                tip_amount_raw is not null
                and not {{ is_non_finite_float('tip_amount_raw') }}
                and not {{ fits_numeric_12_2('tip_amount_raw') }}
            )
            or (
                tolls_amount_raw is not null
                and not {{ is_non_finite_float('tolls_amount_raw') }}
                and not {{ fits_numeric_12_2('tolls_amount_raw') }}
            )
            or (
                improvement_surcharge_amount_raw is not null
                and not {{
                    is_non_finite_float('improvement_surcharge_amount_raw')
                }}
                and not {{
                    fits_numeric_12_2('improvement_surcharge_amount_raw')
                }}
            )
            or (
                total_amount_raw is not null
                and not {{ is_non_finite_float('total_amount_raw') }}
                and not {{ fits_numeric_12_2('total_amount_raw') }}
            )
            or (
                congestion_surcharge_amount_raw is not null
                and not {{
                    is_non_finite_float('congestion_surcharge_amount_raw')
                }}
                and not {{
                    fits_numeric_12_2('congestion_surcharge_amount_raw')
                }}
            )
            or (
                airport_fee_amount_raw is not null
                and not {{ is_non_finite_float('airport_fee_amount_raw') }}
                and not {{ fits_numeric_12_2('airport_fee_amount_raw') }}
            )
        ) as canonical_type_out_of_range,
        (
            {{ is_non_finite_float('trip_distance_raw') }}
            or {{ is_non_finite_float('fare_amount_raw') }}
            or {{ is_non_finite_float('extra_amount_raw') }}
            or {{ is_non_finite_float('mta_tax_amount_raw') }}
            or {{ is_non_finite_float('tip_amount_raw') }}
            or {{ is_non_finite_float('tolls_amount_raw') }}
            or {{
                is_non_finite_float('improvement_surcharge_amount_raw')
            }}
            or {{ is_non_finite_float('total_amount_raw') }}
            or {{
                is_non_finite_float('congestion_surcharge_amount_raw')
            }}
            or {{ is_non_finite_float('airport_fee_amount_raw') }}
        ) as non_finite_numeric_value,
        (
            trip_distance_raw < 0
            and not {{ is_non_finite_float('trip_distance_raw') }}
        ) as negative_trip_distance,
        (
            (
                fare_amount_raw < 0
                and not {{ is_non_finite_float('fare_amount_raw') }}
            )
            or (
                extra_amount_raw < 0
                and not {{ is_non_finite_float('extra_amount_raw') }}
            )
            or (
                mta_tax_amount_raw < 0
                and not {{ is_non_finite_float('mta_tax_amount_raw') }}
            )
            or (
                tip_amount_raw < 0
                and not {{ is_non_finite_float('tip_amount_raw') }}
            )
            or (
                tolls_amount_raw < 0
                and not {{ is_non_finite_float('tolls_amount_raw') }}
            )
            or (
                improvement_surcharge_amount_raw < 0
                and not {{
                    is_non_finite_float('improvement_surcharge_amount_raw')
                }}
            )
            or (
                total_amount_raw < 0
                and not {{ is_non_finite_float('total_amount_raw') }}
            )
            or (
                congestion_surcharge_amount_raw < 0
                and not {{
                    is_non_finite_float('congestion_surcharge_amount_raw')
                }}
            )
            or (
                airport_fee_amount_raw < 0
                and not {{ is_non_finite_float('airport_fee_amount_raw') }}
            )
        ) as negative_monetary_value
    from source_rows
),

normalized as (
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
        source_month_start,
        {{ safe_smallint('vendor_id_raw') }} as vendor_id,
        pickup_datetime,
        dropoff_datetime,
        {{ safe_smallint('passenger_count_raw') }} as passenger_count,
        case
            when {{ is_non_finite_float('trip_distance_raw') }} then null
            else trip_distance_raw
        end as trip_distance,
        {{ safe_smallint('rate_code_id_raw') }} as rate_code_id,
        case upper(trim(store_and_forward_flag_raw))
            when 'Y' then 'Y'
            when 'N' then 'N'
        end as store_and_forward_flag,
        pickup_location_id,
        dropoff_location_id,
        {{ safe_smallint('payment_type_id_raw') }} as payment_type_id,
        {{ safe_numeric_12_2('fare_amount_raw') }} as fare_amount,
        {{ safe_numeric_12_2('extra_amount_raw') }} as extra_amount,
        {{ safe_numeric_12_2('mta_tax_amount_raw') }} as mta_tax_amount,
        {{ safe_numeric_12_2('tip_amount_raw') }} as tip_amount,
        {{ safe_numeric_12_2('tolls_amount_raw') }} as tolls_amount,
        {{
            safe_numeric_12_2('improvement_surcharge_amount_raw')
        }} as improvement_surcharge_amount,
        {{ safe_numeric_12_2('total_amount_raw') }} as total_amount,
        {{
            safe_numeric_12_2('congestion_surcharge_amount_raw')
        }} as congestion_surcharge_amount,
        {{ safe_numeric_12_2('airport_fee_amount_raw') }} as airport_fee_amount,
        (
            extract(epoch from (dropoff_datetime - pickup_datetime)) / 60.0
        )::double precision as trip_duration_minutes,
        pickup_zone_exists,
        dropoff_zone_exists,
        canonical_type_out_of_range,
        non_finite_numeric_value,
        negative_trip_distance,
        negative_monetary_value
    from quality_flags
),

classified as (
    select
        *,
        array_remove(array[
            case when pickup_datetime is null then 'MISSING_PICKUP_DATETIME' end,
            case when dropoff_datetime is null then 'MISSING_DROPOFF_DATETIME' end,
            case when dropoff_datetime < pickup_datetime then 'DROPOFF_BEFORE_PICKUP' end,
            case when canonical_type_out_of_range then 'CANONICAL_TYPE_OUT_OF_RANGE' end,
            case when non_finite_numeric_value then 'NON_FINITE_NUMERIC_VALUE' end,
            case when
                pickup_datetime < source_month_start
                or pickup_datetime >= source_month_start + interval '1 month'
                then 'PICKUP_OUTSIDE_SOURCE_MONTH'
            end,
            case when not pickup_zone_exists then 'UNKNOWN_PICKUP_ZONE' end,
            case when not dropoff_zone_exists then 'UNKNOWN_DROPOFF_ZONE' end,
            case when negative_trip_distance then 'NEGATIVE_TRIP_DISTANCE' end,
            case when trip_duration_minutes <= 0 then 'NON_POSITIVE_DURATION' end,
            case when trip_duration_minutes > 180 then 'EXCESSIVE_DURATION' end,
            case when negative_monetary_value then 'NEGATIVE_MONETARY_VALUE' end
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
            'DROPOFF_BEFORE_PICKUP',
            'CANONICAL_TYPE_OUT_OF_RANGE'
        ]::text[] then 'rejected'
        when cardinality(dq_reason_codes) > 0 then 'quarantined'
        else 'valid'
    end as dq_status,
    dq_reason_codes
from classified
