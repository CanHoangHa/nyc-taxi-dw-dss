select count(*) as actual_members
from {{ ref('dim_time') }}
having count(*) != 1441
