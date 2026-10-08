with minutes as (
    select generate_series(0, 1439) as minute_of_day
),

timed as (
    select
        (minute_of_day + 1)::smallint as time_key,
        make_time(minute_of_day / 60, minute_of_day % 60, 0) as time_of_day,
        (minute_of_day / 60)::smallint as hour_of_day,
        (minute_of_day % 60)::smallint as minute_of_hour,
        minute_of_day::smallint as minute_of_day,
        false as is_unknown
    from minutes
)

select * from timed
union all
select
    0::smallint as time_key,
    null::time as time_of_day,
    null::smallint as hour_of_day,
    null::smallint as minute_of_hour,
    null::smallint as minute_of_day,
    true as is_unknown
