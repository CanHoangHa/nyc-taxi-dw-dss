with expected_columns (column_name, data_type, numeric_precision, numeric_scale) as (
    values
        ('trip_source_key', 'text', null, null),
        ('batch_id', 'uuid', null, null),
        ('source_year', 'smallint', null, null),
        ('source_month', 'smallint', null, null),
        ('source_file', 'text', null, null),
        ('source_row_number', 'bigint', null, null),
        ('vendor_id', 'smallint', null, null),
        ('pickup_datetime', 'timestamp without time zone', null, null),
        ('dropoff_datetime', 'timestamp without time zone', null, null),
        ('passenger_count', 'smallint', null, null),
        ('trip_distance', 'double precision', null, null),
        ('rate_code_id', 'smallint', null, null),
        ('store_and_forward_flag', 'text', null, null),
        ('pickup_location_id', 'integer', null, null),
        ('dropoff_location_id', 'integer', null, null),
        ('payment_type_id', 'smallint', null, null),
        ('fare_amount', 'numeric', 12, 2),
        ('extra_amount', 'numeric', 12, 2),
        ('mta_tax_amount', 'numeric', 12, 2),
        ('tip_amount', 'numeric', 12, 2),
        ('tolls_amount', 'numeric', 12, 2),
        ('improvement_surcharge_amount', 'numeric', 12, 2),
        ('total_amount', 'numeric', 12, 2),
        ('congestion_surcharge_amount', 'numeric', 12, 2),
        ('airport_fee_amount', 'numeric', 12, 2),
        ('trip_duration_minutes', 'double precision', null, null),
        ('dq_status', 'text', null, null),
        ('dq_reason_codes', 'array', null, null)
),

actual_columns as (
    select
        column_name,
        lower(data_type) as data_type,
        numeric_precision,
        numeric_scale
    from information_schema.columns
    where table_schema = '{{ ref("stg_yellow_trip_valid").schema }}'
      and table_name = '{{ ref("stg_yellow_trip_valid").identifier }}'
)

select expected.*
from expected_columns as expected
left join actual_columns as actual using (column_name)
where actual.column_name is null
   or actual.data_type <> expected.data_type
   or (
       expected.numeric_precision is not null
       and actual.numeric_precision <> expected.numeric_precision
   )
   or (
       expected.numeric_scale is not null
       and actual.numeric_scale <> expected.numeric_scale
   )
