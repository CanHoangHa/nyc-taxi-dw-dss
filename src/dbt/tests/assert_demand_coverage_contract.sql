select
    source_year,
    source_month,
    coverage_start_date,
    coverage_end_date,
    valid_trip_count
from {{ ref('mart_demand_coverage') }}
where coverage_start_date is distinct from make_date(source_year, source_month, 1)
    or coverage_end_date is distinct from (
        coverage_start_date + interval '1 month' - interval '1 day'
    )::date
    or valid_trip_count < 0
