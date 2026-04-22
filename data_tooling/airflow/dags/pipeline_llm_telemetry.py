from airflow import DAG
from airflow.operators.empty import EmptyOperator
from airflow.operators.bash import BashOperator
from datetime import datetime, timedelta

# Argumentos por defecto aplicados a todas las tareas del DAG.
# retries=3 + retry_delay=5min: si algo falla por un problema transitorio
# (red caída, Thrift Server ocupado, MinIO timeout), Airflow reintenta
# automáticamente hasta 3 veces antes de marcar la tarea como FAILED.
# Con la idempotencia implementada en ingest_bronze.py (overwritePartitions),
# los reintentos no generan duplicados.
default_args = {
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,  # 5m, 10m, 20m — da tiempo al sistema de recuperarse
}

with DAG(
    dag_id="pipeline_llm_telemetry",
    start_date=datetime(2026, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["lakehouse", "bronze", "dbt"],
    default_args=default_args,
) as dag:
    start = EmptyOperator(task_id="start")

    # 1) Ingesta Bronze desde CSV local (luego se reemplaza por MLflow/MinIO source)
    # Idempotente: overwritePartitions() reemplaza la partición del día en cada retry.
    ingest_to_bronze = BashOperator(
        task_id="ingest_csv_to_bronze",
        bash_command=(
            "python /opt/airflow/tasks/ingest_bronze.py "
            "--input-path /opt/project/docs/tests/locust_09_04_2026_30users/langsmith_metrics_export.csv "
            "--source-type langsmith_csv"
        ),
    )

    # 2) Silver con dbt — transforma raw_llm_traces en una tabla analítica limpia
    transform_silver = BashOperator(
        task_id="dbt_run_silver",
        cwd="/opt/airflow/dbt",
        bash_command="dbt deps && dbt run --profiles-dir /opt/airflow/dbt --select models/silver/stg_agent_runs.sql",
    )

    # 3) Gold con dbt — agrega métricas de negocio
    aggregate_gold = BashOperator(
        task_id="dbt_run_gold",
        cwd="/opt/airflow/dbt",
        bash_command="dbt run --profiles-dir /opt/airflow/dbt --select models/gold",
    )

    end = EmptyOperator(task_id="end")

    start >> ingest_to_bronze >> transform_silver >> aggregate_gold >> end