with source_counts as (
    select
        batch_id,
        count(*) as trip_count,
        sum(total_amount) as total_amount
    from {{ ref('stg_yellow_trip_valid') }}
    group by batch_id
),

fact_counts as (
    select
        batch_id,
        count(*) as trip_count,
        sum(total_amount) as total_amount,
        sum(fact.trip_count) as reported_trip_count
    from {{ ref('fact_trip') }} as fact
    group by batch_id
)

select
    coalesce(source_counts.batch_id, fact_counts.batch_id) as batch_id,
    source_counts.trip_count as source_trips,
    fact_counts.trip_count as fact_trips,
    source_counts.total_amount as source_total_amount,
    fact_counts.total_amount as fact_total_amount
from source_counts
full join fact_counts using (batch_id)
where source_counts.trip_count is distinct from fact_counts.trip_count
   or fact_counts.trip_count is distinct from fact_counts.reported_trip_count
   or source_counts.total_amount is distinct from fact_counts.total_amount
