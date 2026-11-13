"""Run the existing monthly CLI pipeline through the staging handoff."""

from datetime import datetime, timedelta, timezone

from airflow.sdk import DAG, Param
from airflow.providers.standard.operators.bash import BashOperator


PYTHON = "/home/airflow/taxi-venv/bin/python"
DBT = "/home/airflow/taxi-venv/bin/dbt"
DBT_ARGS = "--project-dir src/dbt --profiles-dir src/dbt"

with DAG(
    dag_id="yellow_taxi_ingestion",
    description="Ingest a 2024 month range and refresh the tested staging handoff.",
    start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    max_active_tasks=1,
    default_args={
        "owner": "taxi-dw",
        "retries": 1,
        "retry_delay": timedelta(seconds=30),
        "execution_timeout": timedelta(minutes=30),
    },
    params={
        "year": Param(2024, type="integer", enum=[2024]),
        "start_month": Param(1, type="integer", minimum=1, maximum=12),
        "end_month": Param(3, type="integer", minimum=1, maximum=12),
    },
    tags=["ingestion", "staging"],
) as dag:
    ingest_raw = BashOperator(
        task_id="ingest_raw",
        bash_command=(
            f'{PYTHON} -m taxi_dw.ingestion backfill --year "$SOURCE_YEAR" '
            '--start-month "$START_MONTH" --end-month "$END_MONTH"'
        ),
        env={
            "SOURCE_YEAR": "{{ params.year }}",
            "START_MONTH": "{{ params.start_month }}",
            "END_MONTH": "{{ params.end_month }}",
        },
        append_env=True,
        cwd="/opt/project",
        do_xcom_push=False,
    )
    seed_lookup = BashOperator(
        task_id="seed_lookup",
        bash_command=f"{DBT} seed {DBT_ARGS} --select taxi_zone_lookup",
        cwd="/opt/project",
        do_xcom_push=False,
    )
    build_staging = BashOperator(
        task_id="build_staging",
        bash_command=f"{DBT} run {DBT_ARGS} --select staging",
        cwd="/opt/project",
        do_xcom_push=False,
    )
    test_staging = BashOperator(
        task_id="test_staging",
        bash_command=(
            f"{DBT} test {DBT_ARGS} --select staging source:raw taxi_zone_lookup "
            "--indirect-selection cautious"
        ),
        cwd="/opt/project",
        do_xcom_push=False,
    )
    record_dq_counts = BashOperator(
        task_id="record_dq_counts",
        bash_command=f"{PYTHON} -m taxi_dw.staging_audit",
        cwd="/opt/project",
        do_xcom_push=False,
    )

    ingest_raw >> seed_lookup >> build_staging >> test_staging >> record_dq_counts
