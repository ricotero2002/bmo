"""
Tests de conectividad con servicios cloud administrados.

Estos tests realizan conexiones REALES (sin mocks) a los proveedores cloud.
Se ejecutan únicamente cuando INTEGRATION_ENV=cloud está en el entorno,
y solo si las variables de entorno correspondientes están presentes.

Uso local:
    INTEGRATION_ENV=cloud \
    DB_USER=... DB_PASSWORD=... DB_HOST=... DB_SERVICE_NAME=... \
    PINECONE_API_KEY=... PINECONE_INDEX_NAME=... \
    CELERY_BROKER_URL=amqps://... \
    REDIS_URL=redis://... \
    pytest src/tests/integration/test_cloud_connections.py -v

En CI (GitHub Actions):
    Configurar los secretos en Settings → Secrets and variables → Actions.
    El job "cloud-connectivity" en develop.yml inyecta las variables automáticamente.
"""

import os
import pytest
from dotenv import load_dotenv

# Forzar la carga de .env sobre cualquier variable ya seteada (o de .env.local)
load_dotenv(override=True)

# Saltear todos los tests si no estamos en modo cloud
pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_ENV") != "cloud",
    reason="Solo se ejecuta con INTEGRATION_ENV=cloud"
)

# ─── Oracle Autonomous Database ──────────────────────────────────────────────

@pytest.mark.skipif(
    not all([
        os.getenv("DB_USER"),
        os.getenv("DB_PASSWORD"),
        # Acepta DB_DSN (string completo de OCI) O los parámetros individuales
        os.getenv("DB_DSN") or all([os.getenv("DB_HOST"), os.getenv("DB_SERVICE_NAME")]),
    ]),
    reason="Faltan variables de Oracle DB. Necesitás DB_USER, DB_PASSWORD y (DB_DSN o DB_HOST+DB_SERVICE_NAME)"
)
def test_oracle_db_connection():
    """
    Verifica que oracledb puede conectarse a Oracle Autonomous DB via TLS (sin wallet).

    REQUISITO: mTLS debe estar DESACTIVADO en OCI Console:
      Autonomous Database → tu instancia → DB Connection
      → "Edit" → "Require Mutual TLS (mTLS)" → OFF → Save

    CÓMO OBTENER DB_DSN EN OCI CONSOLE:
      1. Autonomous Database → tu instancia → "DB Connection"
      2. En "TLS", copiar el Connection String (requiere mTLS=OFF), puerto 1521:
         Ejemplo:
           (description=(retry_count=20)(retry_delay=3)
            (address=(protocol=tcps)(port=1521)(host=adb.sa-saopaulo-1.oraclecloud.com))
            (connect_data=(service_name=abc123_high.adb.oraclecloud.com))
            (security=(ssl_server_dn_match=yes)))
      3. Pegarlo como DB_DSN=... en el .env (entre comillas si tiene espacios)

    VARIABLES ALTERNATIVAS (si no usás DB_DSN):
      DB_HOST=adb.sa-saopaulo-1.oraclecloud.com
      DB_PORT=1521  (TLS, NO 1522 que es mTLS)
      DB_SERVICE_NAME=abc123_high.adb.oraclecloud.com
    """
    import ssl
    import oracledb

    ssl_ctx = ssl.create_default_context()

    # Usar DSN completo si está disponible (más fiable), sino construir desde partes
    dsn = os.getenv("DB_DSN") or oracledb.makedsn(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "1521")),
        service_name=os.getenv("DB_SERVICE_NAME"),
    )

    conn = oracledb.connect(
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        dsn=dsn,
        ssl_context=ssl_ctx,
    )
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM DUAL")
    row = cursor.fetchone()
    version = conn.version   # capturar antes de cerrar
    cursor.close()
    conn.close()

    assert row is not None and row[0] == 1, "Oracle DB no devolvió la fila esperada"
    print(f"✅ Oracle DB conectado (TLS) — versión: {version}")

# ─── Aiven PostgreSQL ─────────────────────────────────────────────────────────

@pytest.mark.skipif(
    not os.getenv("AIVEN_PG_URI"),
    reason="Falta la variable AIVEN_PG_URI para el test de PostgreSQL"
)
def test_aiven_postgres_connection():
    """
    Verifica que psycopg puede conectarse a Aiven PostgreSQL usando la Service URI.
    
    CÓMO OBTENER EL DATO EN AIVEN CONSOLE:
      1. Entrar al servicio PostgreSQL.
      2. En la pestaña "Overview", buscar "Connection information".
      3. Copiar la "Service URI" completa.
      4. Pegarla en .env como AIVEN_PG_URI="postgres://..."
    """
    import psycopg

    uri = os.getenv("AIVEN_PG_URI")
    
    try:
        # Usamos una conexión síncrona simple para validar las credenciales y red
        with psycopg.connect(uri) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT version();")
                version = cur.fetchone()[0]
                
                assert version is not None, "PostgreSQL no devolvió versión"
                print(f"✅ Aiven PostgreSQL conectado — Versión: {version}")
    except psycopg.OperationalError as e:
        pytest.fail(f"❌ Error de conexión a Aiven PostgreSQL: {e}")


# ─── OCI Object Storage (S3-compatible) ──────────────────────────────────────

@pytest.mark.skipif(
    not all([
        os.getenv("OCI_ACCESS_KEY"),
        os.getenv("OCI_SECRET_KEY"),
        os.getenv("OCI_NAMESPACE"),
        os.getenv("OCI_REGION"),
    ]),
    reason="Faltan variables de OCI Object Storage (OCI_ACCESS_KEY, OCI_SECRET_KEY, OCI_NAMESPACE, OCI_REGION)"
)
def test_oci_object_storage_connection():
    """
    Verifica que boto3 puede conectarse a OCI Object Storage via API S3-compatible.

    CÓMO OBTENER LOS DATOS EN OCI CONSOLE:
      1. OCI Console → Identity & Security → Users → tu usuario → Customer Secret Keys
         → "Generate Secret Key" → guardar Access Key y Secret
         - OCI_ACCESS_KEY = "Access Key" generada
         - OCI_SECRET_KEY = el secreto mostrado al generar (solo se ve una vez)

      2. OCI Console → Object Storage → tu bucket → "Bucket Details"
         - OCI_NAMESPACE = "Object Storage Namespace" (esquina superior del bucket)
         - OCI_REGION    = región de tu tenancy (ej: sa-saopaulo-1, us-ashburn-1)
         - OCI_BUCKET_NAME = nombre del bucket (ej: bmo-documents)

      3. El endpoint se construye automáticamente:
         https://<namespace>.compat.objectstorage.<region>.oraclecloud.com
    """
    import boto3
    from botocore.exceptions import ClientError

    namespace = os.getenv("OCI_NAMESPACE")
    region = os.getenv("OCI_REGION")
    endpoint_url = f"https://{namespace}.compat.objectstorage.{region}.oraclecloud.com"

    s3 = boto3.client(
        "s3",
        region_name=region,
        endpoint_url=endpoint_url,
        aws_access_key_id=os.getenv("OCI_ACCESS_KEY"),
        aws_secret_access_key=os.getenv("OCI_SECRET_KEY"),
    )

    # Verificar conectividad listando buckets
    response = s3.list_buckets()
    assert "Buckets" in response, "OCI Object Storage no devolvió lista de buckets"
    bucket_names = [b["Name"] for b in response["Buckets"]]
    print(f"✅ OCI Object Storage conectado — buckets: {bucket_names}")

    # Si está configurado, verificar que el bucket específico existe
    bucket_name = os.getenv("OCI_BUCKET_NAME")
    if bucket_name:
        assert bucket_name in bucket_names, (
            f"El bucket '{bucket_name}' no existe. Buckets disponibles: {bucket_names}"
        )
        print(f"✅ Bucket '{bucket_name}' verificado")



# ─── Pinecone Vector Store ────────────────────────────────────────────────────

@pytest.mark.skipif(
    not all([
        os.getenv("PINECONE_API_KEY"),
        os.getenv("PINECONE_INDEX_NAME"),
    ]),
    reason="Faltan variables de Pinecone (PINECONE_API_KEY, PINECONE_INDEX_NAME)"
)
def test_pinecone_connection():
    """
    Verifica que el cliente Pinecone puede conectarse y obtener estadísticas del índice.
    """
    from pinecone import Pinecone

    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    index = pc.Index(os.getenv("PINECONE_INDEX_NAME"))
    stats = index.describe_index_stats()

    assert stats is not None, "Pinecone no devolvió estadísticas del índice"
    print(f"✅ Pinecone conectado — total vectors: {stats.get('total_vector_count', 'N/A')}")

# ─── RabbitMQ / CloudAMQP ─────────────────────────────────────────────────────
'''
@pytest.mark.skipif(
    not os.getenv("CELERY_BROKER_URL"),
    reason="Falta CELERY_BROKER_URL para el test de RabbitMQ"
)
def test_rabbitmq_connection():
    """
    Verifica que pika puede abrir una conexión bloqueante a RabbitMQ (CloudAMQP u otro broker).
    Soporta amqp:// y amqps:// (TLS).
    """
    import pika
    from urllib.parse import urlparse

    broker_url = os.getenv("CELERY_BROKER_URL")
    parsed = urlparse(broker_url)

    ssl_options = None
    if parsed.scheme == "amqps":
        import ssl
        context = ssl.create_default_context()
        ssl_options = pika.SSLOptions(context, parsed.hostname)

    params = pika.ConnectionParameters(
        host=parsed.hostname,
        port=parsed.port or (5671 if parsed.scheme == "amqps" else 5672),
        virtual_host=parsed.path.lstrip("/") or "/",
        credentials=pika.PlainCredentials(parsed.username, parsed.password),
        ssl_options=ssl_options,
        connection_attempts=2,
        retry_delay=2,
    )
    connection = pika.BlockingConnection(params)
    assert connection.is_open, "La conexión a RabbitMQ no está abierta"
    connection.close()
    print(f"✅ RabbitMQ conectado — host: {parsed.hostname}")


# ─── Redis ────────────────────────────────────────────────────────────────────

@pytest.mark.skipif(
    not os.getenv("REDIS_URL"),
    reason="Falta REDIS_URL para el test de Redis"
)
def test_redis_connection():
    """
    Verifica que redis-py puede conectarse y hacer PING al servidor Redis.
    Soporta redis:// y rediss:// (TLS).
    """
    import redis
    from urllib.parse import urlparse

    redis_url = os.getenv("REDIS_URL")
    parsed = urlparse(redis_url)
    
    # Solo pasar ssl_cert_reqs si es rediss://
    kwargs = {
        "socket_connect_timeout": 5,
        "socket_timeout": 5,
    }
    
    if parsed.scheme == "rediss":
        kwargs["ssl_cert_reqs"] = None  # Permite certificados self-signed en Upstash/Redis Cloud

    client = redis.Redis.from_url(redis_url, **kwargs)
    response = client.ping()
    assert response is True, "Redis no respondió al PING"
    info = client.info("server")
    print(f"✅ Redis conectado — versión: {info.get('redis_version', 'N/A')}")
'''
# ─── Kafka / Aiven ──────────────────────────────────────────────────────

@pytest.mark.skipif(
    not all([
        os.getenv("KAFKA_BOOTSTRAP_SERVERS"),
        os.getenv("KAFKA_SASL_USERNAME"),
        os.getenv("KAFKA_SASL_PASSWORD"),
        os.getenv("KAFKA_SSL_CA_LOCATION"),
    ]),
    reason="Faltan variables de Kafka Aiven (KAFKA_BOOTSTRAP_SERVERS, KAFKA_SASL_USERNAME, KAFKA_SASL_PASSWORD)"
)
def test_kafka_connection():
    """
    Verifica que confluent-kafka puede conectarse a Aiven Kafka con SASL_SSL/SCRAM-SHA-256.

    CÓMO OBTENER LOS DATOS EN AIVEN CONSOLE:
      1. Aiven Console → tu servicio Kafka
      2. En "Connection Information":
         - KAFKA_BOOTSTRAP_SERVERS = "Service URI" (ej: kafka-xxx.aivencloud.com:12345)
         - KAFKA_SASL_USERNAME     = usuario (generalmente "avnadmin")
         - KAFKA_SASL_PASSWORD     = password mostrado en la consola
      3. Opcional: bajar el "CA Certificate" y poner la ruta en KAFKA_SSL_CA_LOCATION
         (si no, confluent-kafka usa los CAs del sistema).
    """
    from confluent_kafka import Consumer, KafkaException
    print(os.getenv("KAFKA_BOOTSTRAP_SERVERS"), " ",
    os.getenv("KAFKA_SASL_USERNAME"), " ",
     os.getenv("KAFKA_SASL_PASSWORD")," ",
      os.getenv("KAFKA_SSL_CA_LOCATION"))
    conf = {
        "bootstrap.servers": os.getenv("KAFKA_BOOTSTRAP_SERVERS"),
        "security.protocol": "SASL_SSL",
        "sasl.mechanisms": "SCRAM-SHA-256",
        "sasl.username": os.getenv("KAFKA_SASL_USERNAME"),
        "sasl.password": os.getenv("KAFKA_SASL_PASSWORD"),
        "group.id": "connectivity-test",
        "auto.offset.reset": "earliest",
        # ── Debug SSL ─────────────────────────────────────────────────────────
        "debug": "security,broker",          # ver detalle del handshake TLS
        "ssl.endpoint.identification.algorithm": "none",  # desactiva hostname check
    }
    ca_path = os.getenv("KAFKA_SSL_CA_LOCATION")
    if ca_path:
        # Forzar ruta absoluta para que librdkafka la encuentre seguro
        ca_path = os.path.abspath(ca_path)
        if os.path.exists(ca_path):
            conf["ssl.ca.location"] = ca_path
            print(f"ℹ️  Usando certificado CA: {ca_path}")
        else:
            print(f"❌ ERROR: El archivo CA no existe en: {ca_path}")
            # Fallback a certifi para no romper el test si el archivo falta
            import certifi
            conf["ssl.ca.location"] = certifi.where()
            print(f"ℹ️  Usando certifi como fallback: {conf['ssl.ca.location']}")
    else:
        import certifi
        conf["ssl.ca.location"] = certifi.where()

    consumer = Consumer(conf)
    try:
        # list_topics() verifica que se puede conectar y obtener metadatos del broker
        metadata = consumer.list_topics(timeout=20)
        topic_names = list(metadata.topics.keys())
        assert len(topic_names) > 0, "Kafka no devolvio ningun topic"
        print(f"✅ Kafka (Aiven) conectado — topics: {topic_names}")

        # Verificar que el topic de producción existe
        expected_topic = os.getenv("KAFKA_RAW_DOCUMENTS_TOPIC", "raw-documents")
        if expected_topic in topic_names:
            print(f"✅ Topic '{expected_topic}' encontrado")
        else:
            print(f"⚠️  Topic '{expected_topic}' no encontrado. Topics disponibles: {topic_names}")
    finally:
        consumer.close()