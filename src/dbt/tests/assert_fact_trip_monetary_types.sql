with expected_columns (column_name) as (
    values
        ('fare_amount'),
        ('extra_amount'),
        ('mta_tax_amount'),
        ('tip_amount'),
        ('tolls_amount'),
        ('improvement_surcharge_amount'),
        ('total_amount'),
        ('congestion_surcharge_amount'),
        ('airport_fee_amount')
)

select expected.column_name
from expected_columns as expected
left join information_schema.columns as actual
    on actual.table_schema = '{{ ref("fact_trip").schema }}'
    and actual.table_name = '{{ ref("fact_trip").identifier }}'
    and actual.column_name = expected.column_name
where actual.column_name is null
   or actual.data_type <> 'numeric'
   or actual.numeric_precision <> 12
   or actual.numeric_scale <> 2
