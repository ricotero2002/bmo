import argparse
import sys
import logging
from pyspark.sql import functions as F

# Asegurar acceso a los providers del proyecto
sys.path.append("/opt/project")
from src.providers.lakehouse.spark_utils import get_iceberg_spark_session, ensure_lakehouse_namespaces, expire_old_snapshots

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def register_bronze(ds):
    spark = get_iceberg_spark_session(f"Register_Bronze_{ds}")
    full_table_name = "lakehouse.bronze.raw_llm_traces"

    try:
        ensure_lakehouse_namespaces(spark)
        
        # 1. Crear tabla si no existe
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

        # 2. Leer de la zona de aterrizaje (Landing)
        input_path = f"s3a://bronze/langsmith_raw/date={ds}/"
        logger.info(f"Leyendo archivos Parquet desde {input_path}")
        
        df_new = spark.read.parquet(input_path)
        
        # Agregar timestamp de ingesta
        df_final = df_new.withColumn("ingested_at", F.current_timestamp())

        # 3. Guardado Idempotente: Overwrite de la partición del día
        logger.info(f"Registrando datos en {full_table_name} para la fecha {ds}")
        (
            df_final.writeTo(full_table_name)
            .overwritePartitions()
        )

        total_rows = spark.table(full_table_name).filter(F.col("date") == ds).count()
        logger.info(f"✅ Registro completado. Filas en la partición {ds}: {total_rows}")

        # 4. Limpieza de snapshots
        expire_old_snapshots(spark, full_table_name)

    finally:
        spark.stop()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ds", required=True, help="Execution date YYYY-MM-DD")
    args = parser.parse_args()
    
    register_bronze(args.ds)
