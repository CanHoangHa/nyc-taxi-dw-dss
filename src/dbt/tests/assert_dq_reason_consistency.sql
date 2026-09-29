select trip_source_key, dq_status, dq_reason_codes
from {{ ref('stg_yellow_trip') }}
where (dq_status = 'valid' and cardinality(dq_reason_codes) <> 0)
   or (dq_status <> 'valid' and cardinality(dq_reason_codes) = 0)
