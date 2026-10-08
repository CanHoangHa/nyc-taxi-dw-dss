with unknown_counts as (
    select 'dim_date' as dimension_name, count(*) as member_count
    from {{ ref('dim_date') }} where is_unknown and date_key = 0
    union all
    select 'dim_time', count(*)
    from {{ ref('dim_time') }} where is_unknown and time_key = 0
    union all
    select 'dim_taxi_zone', count(*)
    from {{ ref('dim_taxi_zone') }} where is_unknown and zone_key = repeat('0', 32)
    union all
    select 'dim_vendor', count(*)
    from {{ ref('dim_vendor') }} where is_unknown and vendor_key = repeat('0', 32)
    union all
    select 'dim_payment_type', count(*)
    from {{ ref('dim_payment_type') }} where is_unknown and payment_type_key = repeat('0', 32)
)

select *
from unknown_counts
where member_count != 1
