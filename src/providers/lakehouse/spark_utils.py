import os
import socket
import time
import logging
from pyspark.sql import SparkSession

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _wait_for_spark_connect(host: str, port: int, timeout_total: int = 300, interval: int = 10) -> bool:
    """
    Espera hasta que el puerto gRPC de Spark Connect esté accesible via TCP.
    Esto evita que getOrCreate() quede colgado en un timeout de 10 minutos.

    Returns True si el puerto respondió, False si se agotó el tiempo.
    """
    deadline = time.time() + timeout_total
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        try:
            with socket.create_connection((host, port), timeout=5):
                logger.info(f"✅ Spark Connect disponible en {host}:{port} (intento {attempt})")
                return True
        except (OSError, ConnectionRefusedError):
            remaining = int(deadline - time.time())
            logger.info(
                f"⏳ Spark Connect no disponible aún en {host}:{port} "
                f"(intento {attempt}, {remaining}s restantes) — reintentando en {interval}s..."
            )
            time.sleep(interval)
    return False


def get_iceberg_spark_session(app_name: str) -> SparkSession:
    """
    SparkSession configurada para Iceberg REST + OCI Object Storage.
    Soporta Spark Connect remoto (SPARK_REMOTE) y sesión local (fallback).
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
        raise ValueError(
            "Credenciales no encontradas. "
            "Verificá OCI_ACCESS_KEY y OCI_SECRET_KEY en los secrets del pod."
        )

    remote_url = os.getenv("SPARK_REMOTE")
    builder = SparkSession.builder.appName(app_name)

    if remote_url:
        # Parsear host y puerto de "sc://host:port"
        # Formato esperado: sc://spark-connect-svc.personal-ai.svc.cluster.local:15002
        clean = remote_url.replace("sc://", "")
        host, port_str = clean.rsplit(":", 1)
        port = int(port_str)

        logger.info(f"🌐 Esperando que Spark Connect esté listo en {host}:{port}...")

        # Health check TCP: espera hasta 5 minutos (pod puede estar arrancando)
        ready = _wait_for_spark_connect(host, port, timeout_total=300, interval=10)
        if not ready:
            raise RuntimeError(
                f"Spark Connect en {remote_url} no respondió tras 5 minutos. "
                "Verificá el pod spark-connect con: kubectl logs -n personal-ai -l app=spark-connect"
            )

        # Una vez que el puerto responde, dar 5s extra para que el servidor gRPC
        # termine de inicializarse completamente antes de hacer la primera llamada.
        logger.info("🔄 Puerto accesible. Esperando 5s para inicialización gRPC completa...")
        time.sleep(5)

        logger.info(f"🔌 Conectando a Spark Connect: {remote_url}")
        spark = builder.remote(remote_url).getOrCreate()
        logger.info("✅ Conexión establecida con Spark Connect.")

    else:
        logger.info("🏠 Iniciando Spark Session LOCAL (Legacy)")
        packages = ",".join([
            "org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.5.2",
            "org.apache.iceberg:iceberg-aws-bundle:1.5.2",
            "org.apache.hadoop:hadoop-aws:3.3.4",
        ])
        spark = (
            builder
            .config("spark.jars.packages", packages)
            .config(
                "spark.sql.extensions",
                "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
            )
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
            .config("spark.hadoop.fs.s3a.multipart.size", "134217728")
            .config("spark.hadoop.fs.s3a.bulk.delete.page.size", "250")
            .config("spark.sql.warehouse.dir", "s3a://warehouse/")
            .config("spark.hadoop.fs.s3a.connection.ssl.enabled", ssl_enabled)
            .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
            .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
            .config("spark.hadoop.fs.s3a.checksum.enabled", "false")
            .config("spark.hadoop.fs.s3a.fast.upload", "true")
            .config("spark.hadoop.fs.s3a.fast.upload.buffer", "disk")
            .config("spark.driver.memory", "1g")
            .config("spark.executor.memory", "1g")
            .getOrCreate()
        )

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
