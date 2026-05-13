import os
import logging
from pyspark.sql import SparkSession
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@retry(
    # Spark Connect tarda hasta 120s en arrancar; reintentamos por 3 min
    stop=stop_after_attempt(15),
    wait=wait_exponential(multiplier=1, min=10, max=30),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
def _connect_remote(builder, remote_url: str):
    """Intenta conectar a Spark Connect con reintentos para cold start."""
    return builder.remote(remote_url).getOrCreate()


def get_iceberg_spark_session(app_name: str) -> SparkSession:
    """
    SparkSession configurada para Iceberg REST + OCI Object Storage.
    """
    namespace = os.getenv("OCI_NAMESPACE")
    region = os.getenv("OCI_REGION", "us-ashburn-1")
    oci_bucket = os.getenv("OCI_BUCKET_NAME", "bmo-documents")
    rest_uri = os.getenv(
        "LAKEHOUSE_REST_URI",
        "http://iceberg-rest-svc.personal-ai.svc.cluster.local:8181",
    )

    if namespace:
        access_key = os.getenv("OCI_ACCESS_KEY")
        secret_key = os.getenv("OCI_SECRET_KEY")
        s3_endpoint = f"https://{namespace}.compat.objectstorage.{region}.oraclecloud.com"
        ssl_enabled = "true"
        os.environ.setdefault("AWS_REGION", region)
        os.environ.setdefault("AWS_DEFAULT_REGION", region)
        logger.info(f"SparkSession '{app_name}' → OCI endpoint: {s3_endpoint} | bucket: {oci_bucket}")
    else:
        access_key = os.getenv("MINIO_ROOT_USER", "lakehouse")
        secret_key = os.getenv("MINIO_ROOT_PASSWORD", "lakehouse123")
        s3_endpoint = "http://minio-svc:9000"
        ssl_enabled = "false"
        logger.info(f"SparkSession '{app_name}' → MinIO endpoint: {s3_endpoint}")

    if not access_key or not secret_key:
        raise ValueError("Credenciales no encontradas.")

    packages = ",".join([
        "org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.5.2",
        "org.apache.iceberg:iceberg-aws-bundle:1.5.2",
        "org.apache.hadoop:hadoop-aws:3.3.4",
    ])

    remote_url = os.getenv("SPARK_REMOTE")
    builder = SparkSession.builder.appName(app_name)

    if remote_url:
        logger.info(f"🌐 Conectando a Spark Connect en: {remote_url} ...")
        try:
            spark = _connect_remote(builder, remote_url)
            logger.info("✅ Conexión establecida con Spark Connect.")
        except Exception as e:
            logger.error(f"❌ No se pudo conectar tras reintentos: {e}")
            raise
    else:
        logger.info(f"🏠 Iniciando Spark Session LOCAL (Legacy)")
        spark = (
            builder
            # ── Iceberg ──────────────────────────────────────────────────────────
            .config("spark.jars.packages", packages)
            .config(
                "spark.sql.extensions",
                "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
            )
            # ── Catálogo REST Iceberg ─────────────────────────────────────────────
            .config("spark.sql.defaultCatalog", "lakehouse")
            .config("spark.sql.catalog.lakehouse", "org.apache.iceberg.spark.SparkCatalog")
            .config("spark.sql.catalog.lakehouse.type", "rest")
            .config("spark.sql.catalog.lakehouse.uri", rest_uri)
            .config("spark.sql.catalog.lakehouse.warehouse", "s3a://warehouse/")
            .config("spark.sql.catalog.lakehouse.io-impl", "org.apache.iceberg.aws.s3.S3FileIO")
            .config("spark.sql.catalog.lakehouse.s3.endpoint", s3_endpoint)
            .config("spark.sql.catalog.lakehouse.s3.path-style-access", "true")
            .config("spark.sql.catalog.lakehouse.s3.access-key-id", access_key)
            .config("spark.sql.catalog.lakehouse.s3.secret-access-key", secret_key)
            .config("spark.sql.catalog.lakehouse.s3.region", region)
            .config("spark.sql.catalog.lakehouse.s3.payload-signing-enabled", "true")
            .config("spark.sql.catalog.lakehouse.s3.checksum-enabled", "false")
            .config("spark.sql.catalog.lakehouse.client.region", region)
            # ── S3A Hadoop — credenciales EXPLÍCITAS en el JVM ───────────────────
            .config("spark.hadoop.fs.s3a.endpoint", s3_endpoint)
            .config("spark.hadoop.fs.s3a.access.key", access_key)
            .config("spark.hadoop.fs.s3a.secret.key", secret_key)
            .config("spark.hadoop.fs.s3a.path.style.access", "true")
            .config(
                "spark.hadoop.fs.s3a.aws.credentials.provider",
                "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider",
            )
            .config("spark.hadoop.fs.s3a.signing-algorithm", "AWS4SignerType")
            .config("spark.hadoop.fs.s3a.region", region)
            .config("spark.hadoop.fs.s3a.ssl.channel.mode", "default")
            .config("spark.hadoop.fs.s3a.connection.request.timeout", "60000")
            .config("spark.hadoop.fs.s3a.attempts.maximum", "3")
            .config("spark.hadoop.fs.s3a.connection.establish.timeout", "10000")
            .config("spark.hadoop.fs.s3a.connection.timeout", "60000")
            .config("spark.hadoop.fs.s3a.multipart.enabled", "true")
            .config("spark.hadoop.fs.s3a.multipart.size", "134217728")  # 128MB
            .config("spark.hadoop.fs.s3a.bulk.delete.page.size", "250")
            .config("spark.sql.warehouse.dir", "s3a://warehouse/")
            .config("spark.hadoop.fs.s3a.connection.ssl.enabled", ssl_enabled)
            .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
            .config("spark.hadoop.fs.s3.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
            .config("spark.hadoop.fs.s3a.checksum.enabled", "false")
            .config("spark.hadoop.fs.s3a.fast.upload", "true")
            .config("spark.hadoop.fs.s3a.fast.upload.buffer", "disk")
            .config("spark.driver.memory", "1g")
            .config("spark.executor.memory", "1g")
            .getOrCreate()
        )

    # Verificación removida para compatibilidad con Spark Connect (no hay SparkContext en el cliente)

    return spark


def ensure_lakehouse_namespaces(spark: SparkSession):
    """Crea los namespaces bronze, silver y gold si no existen."""
    for ns in ["bronze", "silver", "gold"]:
        logger.info(f"Asegurando namespace: lakehouse.{ns}")
        spark.sql(f"CREATE NAMESPACE IF NOT EXISTS lakehouse.{ns}")


def expire_old_snapshots(
    spark: SparkSession, full_table_name: str, retain_last: int = 3
):
    """Limpia snapshots antiguos de una tabla Iceberg."""
    try:
        logger.info(f"Expirando snapshots de {full_table_name} (retain_last={retain_last})...")
        spark.sql(
            f"""
            CALL lakehouse.system.expire_snapshots(
                table => '{full_table_name}',
                retain_last => {retain_last}
            )
            """
        )
        logger.info(f"✅ Snapshots expirados en {full_table_name}")
    except Exception as e:
        logger.warning(f"No se pudieron expirar snapshots en {full_table_name}: {e}")