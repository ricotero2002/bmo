"""Airflow DAG skeleton for the telemetry proof-of-concept.

This file intentionally contains only structure and comments.
Goal:
- read CSV or MLflow exports
- land raw data in Bronze
- run Silver and Gold transformations later
"""

# TODO: import DAG and operators only when the flow is ready.
# from airflow import DAG
# from airflow.providers.apache.spark.operators.spark_submit import SparkSubmitOperator
# from airflow.operators.bash import BashOperator

# TODO: define schedule, start date, retries and tags.
# TODO: wire task dependencies: extract -> bronze -> silver -> gold.
