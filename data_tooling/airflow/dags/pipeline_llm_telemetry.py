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
    schedule="@daily",
    catchup=False,
    tags=["lakehouse", "telemetry", "langsmith", "spark", "iceberg"],
    default_args=default_args,
) as dag:
    
    start = EmptyOperator(task_id="start")

    # 1. Extraction: LangSmith -> MinIO (Bronze Parquet)
    extract_task = PythonOperator(
        task_id="extract_from_langsmith",
        python_callable=fetch_yesterday_data,
        op_kwargs={"ds": "{{ ds }}"}, # Injected by Airflow
    )

    # 2. Transformation: Bronze Parquet -> Iceberg Silver
    transform_silver_task = SparkSubmitOperator(
        task_id="spark_transform_silver",
        application="/opt/airflow/tasks/spark_silver.py",
        application_args=["--ds", "{{ ds }}"],
        conn_id="spark_default",
        conf={
            "spark.sql.extensions": "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
            "spark.sql.catalog.lakehouse": "org.apache.iceberg.spark.SparkCatalog",
            # Add other Iceberg/S3 configs if not in spark_default
        }
    )

    # 3. Evaluation & Forensics: Silver -> Iceberg Gold
    evaluate_and_forensics_task = SparkSubmitOperator(
        task_id="spark_evaluate_gold",
        application="/opt/airflow/tasks/spark_evaluator.py",
        application_args=["--ds", "{{ ds }}"],
        conn_id="spark_default",
    )

    # 4. Aggregations: dbt Gold Views (Optional)
    dbt_gold_views = BashOperator(
        task_id="dbt_run_gold_views",
        cwd="/opt/airflow/dbt",
        bash_command="dbt run --profiles-dir /opt/airflow/dbt --select models/gold",
    )

    end = EmptyOperator(task_id="end")

    start >> extract_task >> transform_silver_task >> evaluate_and_forensics_task >> dbt_gold_views >> end