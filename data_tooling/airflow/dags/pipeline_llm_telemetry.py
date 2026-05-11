from airflow import DAG
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.models.param import Param
from datetime import datetime, timedelta
import sys
import os

sys.path.append("/opt/airflow/tasks")
from extract_langsmith import fetch_yesterday_data

default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
}

# ─────────────────────────────────────────────────────────────────────────────
# Configuración de spark-submit para OCI
#
# PROBLEMA ORIGINAL: Las variables de entorno OCI_* están disponibles en Python
# pero S3AFileSystem corre en el JVM y NO las lee automáticamente.
# SOLUCIÓN: Pasarlas como --conf spark.hadoop.fs.s3a.* en la línea de spark-submit,
# usando $VAR para que Bash las expanda en tiempo de ejecución desde el entorno
# del worker donde sí están disponibles.
# ─────────────────────────────────────────────────────────────────────────────
SPARK_CONNECT_BASE = "python3"

# ─────────────────────────────────────────────────────────────────────────────
# DBT base command
#
# FIX: PermissionError en /opt/airflow/dbt/target/partial_parse.msgpack
# Causa: ese directorio fue creado por el scheduler/imagen con el usuario root
#        y el worker corre como uid 50000 (airflow) sin permisos de escritura.
# Solución: redirigir target y logs a /tmp vía variables de entorno.
# ─────────────────────────────────────────────────────────────────────────────
DBT_BASE = (
    "mkdir -p /tmp/dbt_target /tmp/dbt_logs && "
    "export DBT_TARGET_PATH=/tmp/dbt_target && "
    "export DBT_LOG_PATH=/tmp/dbt_logs && "
    "dbt run --profiles-dir /opt/airflow/dbt "
)

with DAG(
    dag_id="pipeline_llm_telemetry",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["lakehouse", "telemetry", "langsmith", "spark", "iceberg"],
    default_args=default_args,
    params={
        "start_time": Param(
            None,
            type=["string", "null"],
            description="ISO format start time (ej: 2026-04-23T17:00:00)",
        ),
        "end_time": Param(
            None,
            type=["string", "null"],
            description="ISO format end time. Por defecto start_time + 1 día",
        ),
        "project": Param(
            os.getenv("LANGCHAIN_PROJECT", "BMO"),
            type="string",
            description="Nombre del proyecto en LangSmith",
        ),
        "sample_fraction": Param(
            1.0,
            type="number",
            description="Fracción de runs a evaluar (0.0 a 1.0)",
        ),
        "max_runs": Param(
            50,
            type="integer",
            description="Máximo de runs a evaluar",
        ),
    },
) as dag:

    start = EmptyOperator(task_id="start")

    # ── 1. Extracción: LangSmith → OCI (Landing Zone, Parquet en chunks) ────
    extract_task = PythonOperator(
        task_id="extract_from_langsmith",
        python_callable=fetch_yesterday_data,
        op_kwargs={
            "ds": "{{ ds }}",
            "project_name": "{{ params.project }}",
            "start_time_custom": "{{ params.start_time }}",
            "end_time_custom": "{{ params.end_time }}",
        },
    )

    # ── 2. Registro: Parquet OCI → Iceberg Bronze ────────────────────────────
    # Los --conf de OCI se expanden en Bash desde las env vars del worker pod.
    register_bronze_task = BashOperator(
        task_id="register_bronze_iceberg",
        execution_timeout=timedelta(minutes=30),
        bash_command=(
            f"{SPARK_CONNECT_BASE} "
            "/opt/airflow/tasks/register_bronze.py --ds {{ ds }}"
        ),
    )

    # ── 3. Transformación Silver: DBT sobre Iceberg Bronze → Silver ──────────
    # --target-path /tmp/dbt_target: evita PermissionError en /opt/airflow/dbt/target/
    dbt_silver_task = BashOperator(
        task_id="dbt_run_silver",
        execution_timeout=timedelta(minutes=20),
        cwd="/opt/airflow/dbt",
        bash_command=DBT_BASE + "--select models/silver",
    )


    # ── 4. Evaluación & Forense: Silver → Iceberg Gold ───────────────────────
    evaluate_and_forensics_task = BashOperator(
        task_id="spark_evaluate_gold",
        execution_timeout=timedelta(minutes=45),
        bash_command=(
            f"{SPARK_CONNECT_BASE} "
            "/opt/airflow/tasks/spark_evaluator.py "
            "--ds {{ ds }} "
            "--sample-fraction {{ params.sample_fraction }} "
            "--max-runs {{ params.max_runs }}"
        ),
    )

    # ── 5. Agregaciones Gold: DBT ────────────────────────────────────────────
    dbt_gold_task = BashOperator(
        task_id="dbt_run_gold",
        execution_timeout=timedelta(minutes=20),
        cwd="/opt/airflow/dbt",
        bash_command=DBT_BASE + "--select models/gold",
    )

    end = EmptyOperator(task_id="end")

    start >> extract_task >> register_bronze_task >> dbt_silver_task >> evaluate_and_forensics_task >> dbt_gold_task >> end