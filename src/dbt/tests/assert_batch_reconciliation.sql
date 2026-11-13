with raw_counts as (
    select batch_id, count(*) as raw_count
    from {{ source('raw', 'yellow_trip') }}
    group by batch_id
),

staging_counts as (
    select
        batch_id,
        count(*) as staging_count,
        count(*) filter (where dq_status = 'valid') as valid_count,
        count(*) filter (where dq_status = 'quarantined') as quarantined_count,
        count(*) filter (where dq_status = 'rejected') as rejected_count
    from {{ ref('stg_yellow_trip') }}
    group by batch_id
)

select *
from raw_counts
full join staging_counts using (batch_id)
where raw_count is distinct from staging_count
   or staging_count is distinct from valid_count + quarantined_count + rejected_count
