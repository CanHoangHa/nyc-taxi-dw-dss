with vendor_codes as (
    select distinct vendor_id
    from {{ ref('stg_yellow_trip_valid') }}
    where vendor_id is not null
),

vendors as (
    select
        md5('dim_vendor|' || vendor_id::text) as vendor_key,
        vendor_id,
        case vendor_id
            when 1 then 'Creative Mobile Technologies, LLC'
            when 2 then 'Curb Mobility, LLC'
            when 6 then 'Myle Technologies Inc'
            when 7 then 'Helix'
            else 'Unmapped vendor code ' || vendor_id::text
        end as vendor_name,
        false as is_unknown
    from vendor_codes
)

select * from vendors
union all
select
    repeat('0', 32) as vendor_key,
    null::smallint as vendor_id,
    'Unknown / missing vendor ID'::text as vendor_name,
    true as is_unknown
