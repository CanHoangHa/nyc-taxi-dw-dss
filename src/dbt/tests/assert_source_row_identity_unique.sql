select
    source_dataset,
    source_year,
    source_month,
    source_row_number,
    count(*) as row_count
from {{ ref('stg_yellow_trip') }}
group by source_dataset, source_year, source_month, source_row_number
having count(*) > 1
