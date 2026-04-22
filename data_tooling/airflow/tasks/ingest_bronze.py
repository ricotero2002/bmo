"""CSV/MLflow telemetry ingestion job for Bronze Iceberg.

Estrategia de idempotencia: Iceberg overwritePartitions()
---------------------------------------------------------
Se elige la Opción C (overwritePartitions) porque:
  1. Es la más nativa de Iceberg: el reemplazo es ATÓMICO. Si falla a mitad,
     el snapshot no se confirma y la tabla queda en su estado anterior.
  2. Compatible con particionado por días: si la misma fecha se reprocesa
     (retry de Airflow), solo se reemplaza la partición afectada.
  3. Sin necesidad de clave primaria (como MERGE requeriría), lo que la hace
     más robusta frente a cambios de schema del CSV de origen.
  4. A escala, es más eficiente que DELETE+INSERT porque no genera archivos de
     deletion sino que simplemente apunta el snapshot a los nuevos archivos.
"""

import argparse
import os

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import TimestampType


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest telemetry CSV into Bronze Iceberg")
    parser.add_argument(
        "--input-path",
        default="/opt/project/docs/tests/locust_09_04_2026_30users/langsmith_metrics_export.csv",
        help="CSV path visible from the runtime container",
    )
    parser.add_argument("--source-type", default="langsmith_csv", help="Source label for lineage")
    parser.add_argument("--catalog", default="lakehouse", help="Iceberg catalog name")
    parser.add_argument("--target-table", default="raw_llm_traces", help="Target Bronze table name")
    return parser.parse_args()


def build_spark_session() -> SparkSession:
    minio_user = os.getenv("MINIO_ROOT_USER", "lakehouse")
    minio_password = os.getenv("MINIO_ROOT_PASSWORD", "lakehouse123")
    lakehouse_rest_uri = os.getenv("LAKEHOUSE_REST_URI", "http://host.docker.internal:8181")
    lakehouse_s3_endpoint = os.getenv("LAKEHOUSE_S3_ENDPOINT", "http://host.docker.internal:9000")

    # Ensure AWS_REGION is set for the underlying AWS SDK used by Iceberg S3FileIO
    os.environ["AWS_REGION"] = os.getenv("AWS_REGION", "us-east-1")

    return (
        SparkSession.builder.appName("ingest-bronze-llm-traces")
        .config("spark.jars.packages", "org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.5.2,org.apache.iceberg:iceberg-aws-bundle:1.5.2")
        .config("spark.sql.defaultCatalog", "lakehouse")
        .config("spark.sql.catalog.lakehouse", "org.apache.iceberg.spark.SparkCatalog")
        .config("spark.sql.catalog.lakehouse.type", "rest")
        .config("spark.sql.catalog.lakehouse.uri", lakehouse_rest_uri)
        .config("spark.sql.catalog.lakehouse.warehouse", "s3://warehouse/")
        .config("spark.sql.catalog.lakehouse.io-impl", "org.apache.iceberg.aws.s3.S3FileIO")
        .config("spark.sql.catalog.lakehouse.s3.endpoint", lakehouse_s3_endpoint)
        .config("spark.sql.catalog.lakehouse.s3.path-style-access", "true")
        .config("spark.sql.catalog.lakehouse.s3.access-key-id", minio_user)
        .config("spark.sql.catalog.lakehouse.s3.secret-access-key", minio_password)
        .config("spark.hadoop.fs.s3a.endpoint", lakehouse_s3_endpoint)
        .config("spark.hadoop.fs.s3a.access.key", minio_user)
        .config("spark.hadoop.fs.s3a.secret.key", minio_password)
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false")
        .config("spark.executor.memory", "2g")
        .config("spark.memory.fraction", "0.8")
        .config("spark.sql.shuffle.partitions", "200")
        # Habilitar el modo de sobrescritura dinámica de particiones para overwritePartitions()
        .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
        .getOrCreate()
    )


def normalize_columns(df):
    column_map = {
        "Run ID": "run_id",
        "Name": "name",
        "Start Time": "start_time",
        "Latency (ms)": "latency_ms",
        "Status": "status",
        "User ID": "user_id",
        "Thread ID": "thread_id",
        "Test Type": "test_type",
        "Tags": "tags",
        "Prompt Tokens": "prompt_tokens",
        "Completion Tokens": "completion_tokens",
        "Total Tokens": "total_tokens",
        "Total Cost ($)": "total_cost_usd",
    }

    for old_name, new_name in column_map.items():
        if old_name in df.columns:
            df = df.withColumnRenamed(old_name, new_name)

    return (
        df.withColumn("start_time", F.col("start_time").cast(TimestampType()))
        .withColumn("ingested_at", F.current_timestamp())
        .withColumn("source_type", F.lit("langsmith_csv"))
    )


def _ensure_namespaces(spark: SparkSession, catalog: str) -> None:
    """Crea los namespaces del lakehouse si no existen."""
    for ns in ["default", "bronze", "silver", "gold"]:
        spark.sql(f"CREATE NAMESPACE IF NOT EXISTS {catalog}.{ns}")


def _ensure_bronze_table(spark: SparkSession, full_table_name: str) -> None:
    """Crea la tabla Bronze con particionado por día si no existe.

    La partición es days(ingested_at) — no start_time — porque:
    - ingested_at es cuándo llegó el dato (determinista en un re-run del mismo día)
    - start_time puede venir de días pasados, generando particiones inesperadas
    - Airflow corre @daily, así que un re-run siempre toca la misma partición
    """
    spark.sql(
        f"""
        CREATE TABLE IF NOT EXISTS {full_table_name} (
            run_id STRING,
            name STRING,
            start_time TIMESTAMP,
            latency_ms DOUBLE,
            status STRING,
            user_id STRING,
            thread_id STRING,
            test_type STRING,
            tags STRING,
            prompt_tokens BIGINT,
            completion_tokens BIGINT,
            total_tokens BIGINT,
            total_cost_usd DOUBLE,
            source_type STRING,
            ingested_at TIMESTAMP
        )
        USING iceberg
        PARTITIONED BY (days(ingested_at))
        TBLPROPERTIES (
            'write.parquet.compression-codec' = 'zstd',
            'history.expire.max-snapshot-age-ms' = '604800000'
        )
        """
    )


def _expire_old_snapshots(spark: SparkSession, full_table_name: str) -> None:
    """Limpia snapshots Iceberg de más de 7 días para liberar espacio en MinIO.

    Iceberg es ACID: cada escritura crea un nuevo snapshot. Sin expiración,
    los archivos .parquet y .avro de snapshots viejos se acumulan indefinidamente.
    Esta función se llama al final de cada ingesta exitosa.
    """
    try:
        spark.sql(
            f"""
            CALL lakehouse.system.expire_snapshots(
                table => '{full_table_name}',
                older_than => TIMESTAMP '{__import__('datetime').datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}',
                retain_last => 3
            )
            """
        )
        print(f"Snapshots antiguos expirados en {full_table_name} (se conservan los últimos 3).")
    except Exception as e:
        # No es crítico — la tabla sigue funcionando correctamente
        print(f"Advertencia: no se pudieron expirar snapshots: {e}")


def main() -> None:
    args = parse_args()
    spark = build_spark_session()
    full_table_name = f"{args.catalog}.bronze.{args.target_table}"

    try:
        _ensure_namespaces(spark, args.catalog)
        _ensure_bronze_table(spark, full_table_name)

        df_raw = spark.read.option("header", "true").option("inferSchema", "true").csv(args.input_path)
        df_clean = (
            normalize_columns(df_raw)
            .withColumn("source_type", F.lit(args.source_type))
            .select(
                "run_id", "name", "start_time", "latency_ms", "status",
                "user_id", "thread_id", "test_type", "tags",
                "prompt_tokens", "completion_tokens", "total_tokens",
                "total_cost_usd", "source_type", "ingested_at",
            )
        )

        # --- IDEMPOTENCIA: overwritePartitions() ---
        # Reemplaza atómicamente solo las particiones (días) presentes en df_clean.
        # Si Airflow reintenta la tarea del mismo día, los datos existentes de ese
        # día se reemplazan en lugar de duplicarse. ACID garantiza que si la
        # escritura falla a mitad, la tabla permanece en su estado anterior.
        (
            df_clean.writeTo(full_table_name)
            .overwritePartitions()
        )

        total_rows = spark.sql(f"SELECT count(*) AS total FROM {full_table_name}").collect()[0][0]
        print(f"Ingesta Bronze completada en {full_table_name}. Total rows: {total_rows}")

        # Limpieza de snapshots viejos para liberar espacio en MinIO
        _expire_old_snapshots(spark, full_table_name)

    finally:
        spark.stop()


if __name__ == "__main__":
    main()