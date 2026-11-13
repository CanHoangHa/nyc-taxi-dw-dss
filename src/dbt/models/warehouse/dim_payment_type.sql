with payment_codes as (
    select distinct payment_type_id
    from {{ ref('stg_yellow_trip_valid') }}
    where payment_type_id is not null
),

payment_types as (
    select
        md5('dim_payment_type|' || payment_type_id::text) as payment_type_key,
        payment_type_id,
        case payment_type_id
            when 0 then 'Flex Fare trip'
            when 1 then 'Credit card'
            when 2 then 'Cash'
            when 3 then 'No charge'
            when 4 then 'Dispute'
            when 5 then 'Unknown payment type (TLC code 5)'
            when 6 then 'Voided trip'
            else 'Unmapped payment type code ' || payment_type_id::text
        end as payment_type_name,
        false as is_unknown
    from payment_codes
)

select * from payment_types
union all
select
    repeat('0', 32) as payment_type_key,
    null::smallint as payment_type_id,
    'Unknown / missing payment type ID'::text as payment_type_name,
    true as is_unknown
