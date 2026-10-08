with bounds as (
    select
        least(min(pickup_datetime::date), min(dropoff_datetime::date)) as first_date,
        greatest(max(pickup_datetime::date), max(dropoff_datetime::date)) as last_date
    from {{ ref('stg_yellow_trip_valid') }}
),

calendar as (
    select generate_series(
        first_date::timestamp,
        last_date::timestamp,
        interval '1 day'
    )::date as calendar_date
    from bounds
),

dated as (
    select
        to_char(calendar_date, 'YYYYMMDD')::integer as date_key,
        calendar_date,
        extract(isoyear from calendar_date)::smallint as iso_year,
        extract(week from calendar_date)::smallint as iso_week,
        extract(isodow from calendar_date)::smallint as iso_day_of_week,
        extract(year from calendar_date)::smallint as calendar_year,
        extract(quarter from calendar_date)::smallint as calendar_quarter,
        extract(month from calendar_date)::smallint as calendar_month,
        extract(day from calendar_date)::smallint as day_of_month,
        (extract(isodow from calendar_date) in (6, 7)) as is_weekend,
        false as is_unknown
    from calendar
)

select * from dated
union all
select
    0 as date_key,
    null::date as calendar_date,
    null::smallint as iso_year,
    null::smallint as iso_week,
    null::smallint as iso_day_of_week,
    null::smallint as calendar_year,
    null::smallint as calendar_quarter,
    null::smallint as calendar_month,
    null::smallint as day_of_month,
    null::boolean as is_weekend,
    true as is_unknown
