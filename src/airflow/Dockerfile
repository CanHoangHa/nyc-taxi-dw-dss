FROM apache/airflow:3.3.2-python3.11

# Keep dbt/project packages isolated from Airflow's dependencies.
COPY requirements.txt /tmp/taxi-requirements.txt
RUN python -m venv /home/airflow/taxi-venv \
    && /home/airflow/taxi-venv/bin/pip install --no-cache-dir -r /tmp/taxi-requirements.txt

WORKDIR /opt/project
