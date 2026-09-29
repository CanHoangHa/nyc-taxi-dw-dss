select *
from {{ ref('stg_yellow_trip') }}
where dq_status = 'valid'
