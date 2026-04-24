from airflow import DAG
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import PythonOperator
from airflow.providers.apache.spark.operators.spark_submit import SparkSubmitOperator
from airflow.operators.bash import BashOperator
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
) as dag:
    
    start = EmptyOperator(task_id="start")

    # 1. Extracción: LangSmith -> MinIO (Landing Zone - Parquet en chunks)
    extract_task = PythonOperator(
        task_id="extract_from_langsmith",
        python_callable=fetch_yesterday_data,
        op_kwargs={"ds": "{{ ds }}"},
    )

    # 2. Registro: Landing Parquet -> Iceberg Bronze
    register_bronze_task = SparkSubmitOperator(
        task_id="register_bronze_iceberg",
        application="/opt/airflow/tasks/register_bronze.py",
        application_args=["--ds", "{{ ds }}"],
        conn_id="spark_default",
    )

    # 3. Transformación Silver: DBT sobre Spark (Iceberg Bronze -> Iceberg Silver)
    # dbt se conecta al Thrift Server y ejecuta SQL nativo en Spark
    dbt_silver_task = BashOperator(
        task_id="dbt_run_silver",
        cwd="/opt/airflow/dbt",
        bash_command="dbt run --profiles-dir /opt/airflow/dbt --select models/silver",
    )

    # 4. Evaluación & Forense: Silver -> Iceberg Gold (Spark con Checkpoints)
    evaluate_and_forensics_task = SparkSubmitOperator(
        task_id="spark_evaluate_gold",
        application="/opt/airflow/tasks/spark_evaluator.py",
        application_args=["--ds", "{{ ds }}"],
        conn_id="spark_default",
    )

    # 5. Agregaciones Gold: DBT (Iceberg Gold Eval -> Vistas de Negocio)
    dbt_gold_task = BashOperator(
        task_id="dbt_run_gold",
        cwd="/opt/airflow/dbt",
        bash_command="dbt run --profiles-dir /opt/airflow/dbt --select models/gold",
    )

    end = EmptyOperator(task_id="end")

    # Orquestación: Flujo completo del Lakehouse
    start >> extract_task >> register_bronze_task >> dbt_silver_task >> evaluate_and_forensics_task >> dbt_gold_task >> end