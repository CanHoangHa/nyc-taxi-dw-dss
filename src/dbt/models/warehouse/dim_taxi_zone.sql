with zones as (
    select
        md5('dim_taxi_zone|' || location_id::text) as zone_key,
        location_id,
        borough,
        zone_name,
        service_zone,
        false as is_unknown
    from {{ ref('taxi_zone_lookup') }}
)

select * from zones
union all
select
    repeat('0', 32) as zone_key,
    null::integer as location_id,
    'Unknown'::text as borough,
    'Unknown / missing location ID'::text as zone_name,
    'Unknown'::text as service_zone,
    true as is_unknown
