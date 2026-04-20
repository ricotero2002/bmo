"""Spark job skeleton that lands raw telemetry into Iceberg Bronze.

Expected future responsibilities:
- read a CSV export or MLflow runs
- apply only minimal normalization
- write raw rows to lakehouse.bronze.* tables
"""

# TODO: parse CLI arguments such as input_path, source_type and run_date.
# TODO: build SparkSession with the Lakehouse REST catalog.
# TODO: read source data and keep the schema as close as possible to the raw input.
# TODO: write to lakehouse.bronze.llm_traces or lakehouse.bronze.raw_llm_traces.
