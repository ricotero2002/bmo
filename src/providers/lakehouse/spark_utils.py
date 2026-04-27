import os
import logging
from pyspark.sql import SparkSession

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_iceberg_spark_session(app_name: str) -> SparkSession:
    """
    Devuelve una sesión de Spark preconfigurada para usar el catálogo REST de Iceberg
    y almacenamiento MinIO/S3.
    """
    minio_user = os.getenv("MINIO_ROOT_USER", "lakehouse")
    minio_password = os.getenv("MINIO_ROOT_PASSWORD", "lakehouse123")
    rest_uri = os.getenv("LAKEHOUSE_REST_URI", "http://host.docker.internal:8181")
    s3_endpoint = os.getenv("LAKEHOUSE_S3_ENDPOINT", "http://host.docker.internal:9000")
    aws_region = os.getenv("AWS_REGION", "us-east-1")

    logger.info(f"Creando SparkSession '{app_name}' con Iceberg REST en {rest_uri}")

    return (
        SparkSession.builder.appName(app_name)
        # Packages necesarios para Iceberg y AWS/S3
        .config("spark.jars.packages", "org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.5.2,org.apache.iceberg:iceberg-aws-bundle:1.5.2")
        .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
        .config("spark.sql.defaultCatalog", "lakehouse")
        .config("spark.sql.catalog.lakehouse", "org.apache.iceberg.spark.SparkCatalog")
        .config("spark.sql.catalog.lakehouse.type", "rest")
        .config("spark.sql.catalog.lakehouse.uri", rest_uri)
        .config("spark.sql.catalog.lakehouse.warehouse", "s3://warehouse/")
        .config("spark.sql.catalog.lakehouse.io-impl", "org.apache.iceberg.aws.s3.S3FileIO")
        .config("spark.sql.catalog.lakehouse.s3.endpoint", s3_endpoint)
        .config("spark.sql.catalog.lakehouse.s3.path-style-access", "true")
        .config("spark.sql.catalog.lakehouse.s3.access-key-id", minio_user)
        .config("spark.sql.catalog.lakehouse.s3.secret-access-key", minio_password)
        .config("spark.hadoop.fs.s3a.endpoint", s3_endpoint)
        .config("spark.hadoop.fs.s3a.access.key", minio_user)
        .config("spark.hadoop.fs.s3a.secret.key", minio_password)
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false")
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
        .config("spark.hadoop.fs.s3.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
        .config("spark.sql.catalog.lakehouse.s3.region", aws_region)
        .getOrCreate()
    )

def ensure_lakehouse_namespaces(spark: SparkSession):
    """Crea los namespaces bronze, silver y gold si no existen en el catálogo lakehouse."""
    for ns in ["bronze", "silver", "gold"]:
        logger.info(f"Asegurando namespace: lakehouse.{ns}")
        spark.sql(f"CREATE NAMESPACE IF NOT EXISTS lakehouse.{ns}")

def expire_old_snapshots(spark: SparkSession, full_table_name: str, retain_last: int = 3):
    """Limpia snapshots antiguos para liberar espacio."""
    try:
        logger.info(f"Expirando snapshots antiguos de {full_table_name}...")
        spark.sql(
            f"""
            CALL lakehouse.system.expire_snapshots(
                table => '{full_table_name}',
                retain_last => {retain_last}
            )
            """
        )
    except Exception as e:
        logger.warning(f"No se pudieron expirar snapshots en {full_table_name}: {e}")
