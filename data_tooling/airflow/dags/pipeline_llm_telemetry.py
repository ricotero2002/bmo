from airflow import DAG
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import PythonOperator
from airflow.providers.apache.spark.operators.spark_submit import SparkSubmitOperator
from airflow.operators.bash import BashOperator
from airflow.models.param import Param
from datetime import datetime, timedelta
import sys
import os

# Import the extraction logic
sys.path.append("/opt/airflow/tasks")
from extract_langsmith import fetch_yesterday_data

default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
}

with DAG(
    dag_id="pipeline_llm_telemetry",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["lakehouse", "telemetry", "langsmith", "spark", "iceberg"],
    default_args=default_args,
    params={
        "start_time": Param(None, type=["string", "null"], description="ISO format start time (e.g., 2026-04-23T17:00:00)"),
        "end_time": Param(None, type=["string", "null"], description="ISO format end time. Defaults to start_time + 1 day"),
        "project": Param(os.getenv("LANGCHAIN_PROJECT", "BMO"), type="string", description="LangSmith project name")
    },
) as dag:
    
    start = EmptyOperator(task_id="start")

    # 1. Extracción: LangSmith -> MinIO (Landing Zone - Parquet en chunks)
    extract_task = PythonOperator(
        task_id="extract_from_langsmith",
        python_callable=fetch_yesterday_data,
        op_kwargs={
            "ds": "{{ ds }}",
            "project_name": "{{ params.project }}",
            "start_time_custom": "{{ params.start_time }}",
            "end_time_custom": "{{ params.end_time }}"
        },
    )

    # 2. Registro: Landing Parquet -> Iceberg Bronze
    register_bronze_task = BashOperator(
        task_id="register_bronze_iceberg",
        bash_command="spark-submit --master 'local[*]' --packages 'org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.5.2,org.apache.iceberg:iceberg-aws-bundle:1.5.2,org.apache.hadoop:hadoop-aws:3.3.4' --name register_bronze /opt/airflow/tasks/register_bronze.py --ds {{ ds }}",
    )

    # 3. Transformación Silver: DBT sobre Spark (Iceberg Bronze -> Iceberg Silver)
    # dbt se conecta al Thrift Server y ejecuta SQL nativo en Spark
    dbt_silver_task = BashOperator(
        task_id="dbt_run_silver",
        cwd="/opt/airflow/dbt",
        bash_command="dbt debug --profiles-dir /opt/airflow/dbt && dbt deps --profiles-dir /opt/airflow/dbt && dbt run --profiles-dir /opt/airflow/dbt --select models/silver",
    )

    # 4. Evaluación & Forense: Silver -> Iceberg Gold (Spark con Checkpoints)
    evaluate_and_forensics_task = BashOperator(
        task_id="spark_evaluate_gold",
        bash_command="spark-submit --master 'local[*]' --packages 'org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.5.2,org.apache.iceberg:iceberg-aws-bundle:1.5.2,org.apache.hadoop:hadoop-aws:3.3.4' --name spark_evaluate_gold /opt/airflow/tasks/spark_evaluator.py --ds {{ ds }}",
    )

    # 5. Agregaciones Gold: DBT (Iceberg Gold Eval -> Vistas de Negocio)
    dbt_gold_task = BashOperator(
        task_id="dbt_run_gold",
        cwd="/opt/airflow/dbt",
        bash_command="dbt deps --profiles-dir /opt/airflow/dbt && dbt run --profiles-dir /opt/airflow/dbt --select models/gold",
    )

    end = EmptyOperator(task_id="end")

    # Orquestación: Flujo completo del Lakehouse
    start >> extract_task >> register_bronze_task >> dbt_silver_task >> evaluate_and_forensics_task >> dbt_gold_task >> end