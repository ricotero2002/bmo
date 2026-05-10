import argparse
import os
import sys
import logging
from pyspark.sql import functions as F

sys.path.append("/opt/project")
from src.providers.lakehouse.spark_utils import (
    get_iceberg_spark_session,
    ensure_lakehouse_namespaces,
    expire_old_snapshots,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def download_parquets_from_oci(ds: str, local_dir: str) -> int:
    """Descarga los Parquets de la landing zone desde OCI via boto3.
    Retorna el número de archivos descargados.
    """
    import boto3, pathlib
    namespace = os.getenv("OCI_NAMESPACE")
    region = os.getenv("OCI_REGION", "us-ashburn-1")
    ak = os.getenv("OCI_ACCESS_KEY")
    sk = os.getenv("OCI_SECRET_KEY")
    endpoint = f"https://{namespace}.compat.objectstorage.{region}.oraclecloud.com"

    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=ak,
        aws_secret_access_key=sk,
        region_name=region,
        config=boto3.session.Config(
            signature_version="s3v4",
            s3={"payload_signing_enabled": True, "addressing_style": "path"},
        ),
    )

    prefix = f"langsmith_raw/date={ds}/"
    paginator = s3.get_paginator("list_objects_v2")
    pages = paginator.paginate(Bucket="bronze", Prefix=prefix)

    pathlib.Path(local_dir).mkdir(parents=True, exist_ok=True)
    count = 0
    for page in pages:
        for obj in page.get("Contents", []):
            key = obj["Key"]
            filename = os.path.basename(key)
            local_path = os.path.join(local_dir, filename)
            logger.info(f"Descargando s3://bronze/{key} → {local_path}")
            s3.download_file("bronze", key, local_path)
            count += 1

    return count


def register_bronze(ds: str):
    spark = get_iceberg_spark_session(f"Register_Bronze_{ds}")
    full_table_name = "lakehouse.bronze.raw_llm_traces"
    local_tmp = f"/tmp/bronze_landing_{ds}"

    try:
        ensure_lakehouse_namespaces(spark)

        # 1. Crear tabla Iceberg si no existe
        spark.sql(f"""
            CREATE TABLE IF NOT EXISTS {full_table_name} (
                run_id STRING,
                date STRING,
                start_time STRING,
                status STRING,
                error_message STRING,
                latency_ms DOUBLE,
                prompt_tokens BIGINT,
                completion_tokens BIGINT,
                total_tokens BIGINT,
                total_cost_usd DOUBLE,
                inputs_json STRING,
                outputs_json STRING,
                tools_used STRING,
                ingested_at TIMESTAMP
            )
            USING iceberg
            PARTITIONED BY (date)
            TBLPROPERTIES (
                'write.parquet.compression-codec' = 'zstd'
            )
        """)

        # 2. Descargar Parquets desde OCI via boto3 (evita el 403 de Hadoop S3A con OCI)
        logger.info(f"Descargando Parquets de OCI para fecha {ds} → {local_tmp}")
        n_files = download_parquets_from_oci(ds, local_tmp)
        if n_files == 0:
            logger.warning(f"⚠️ No hay archivos en la landing zone para {ds}. Saliendo.")
            return

        logger.info(f"Descargados {n_files} archivos. Leyendo con Spark desde {local_tmp}")
        df_new = spark.read.parquet(local_tmp)
        logger.info(f"Filas leídas: {df_new.count()}")

        # 3. Agregar timestamp de ingesta
        df_final = df_new.withColumn("ingested_at", F.current_timestamp())

        # 4. Overwrite idempotente de la partición del día
        logger.info(f"Registrando en {full_table_name} para fecha {ds}...")
        df_final.writeTo(full_table_name).overwritePartitions()

        total_rows = (
            spark.table(full_table_name).filter(F.col("date") == ds).count()
        )
        logger.info(f"✅ Registro completado. Filas en partición {ds}: {total_rows}")

        # 5. Limpiar snapshots viejos
        expire_old_snapshots(spark, full_table_name)

    finally:
        spark.stop()
        # Limpiar temporales locales
        import shutil
        if os.path.exists(local_tmp):
            shutil.rmtree(local_tmp)
            logger.info(f"Limpiado directorio temporal {local_tmp}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ds", required=True, help="Fecha de ejecución YYYY-MM-DD")
    args = parser.parse_args()

    try:
        register_bronze(args.ds)
        logger.info("🚀 Script finished successfully.")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Critical error in register_bronze: {e}", exc_info=True)
        sys.exit(1)