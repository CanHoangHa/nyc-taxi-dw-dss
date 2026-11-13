{% macro is_non_finite_float(column_name) -%}
    {{ column_name }}::text in ('NaN', 'Infinity', '-Infinity')
{%- endmacro %}

{% macro fits_numeric_12_2(column_name) -%}
    (
        not {{ is_non_finite_float(column_name) }}
        and round({{ column_name }}::numeric, 2)
            between -9999999999.99::numeric and 9999999999.99::numeric
    )
{%- endmacro %}

{% macro safe_numeric_12_2(column_name) -%}
    case
        when {{ fits_numeric_12_2(column_name) }}
            then {{ column_name }}::numeric(12, 2)
    end
{%- endmacro %}

{% macro safe_smallint(column_name) -%}
    case
        when {{ column_name }} between -32768 and 32767
            then {{ column_name }}::smallint
    end
{%- endmacro %}
