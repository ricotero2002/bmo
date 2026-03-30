import os
import io
import uuid
import pytest
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from dotenv import load_dotenv

# Cargar variables de entorno desde .env (override para asegurar que tome las locales)
load_dotenv(override=True)

# Habilitar logging de botocore solo si es necesario depurar headers
import logging
# logging.getLogger('botocore').setLevel(logging.DEBUG)

# Configuración de salteo si faltan variables
REQUIRED_VARS = [
    "OCI_ACCESS_KEY",
    "OCI_SECRET_KEY",
    "OCI_NAMESPACE",
    "OCI_REGION",
    "OCI_BUCKET_NAME"
]

pytestmark = pytest.mark.skipif(
    not all(os.getenv(v) for v in REQUIRED_VARS),
    reason=f"Faltan variables para OCI: {REQUIRED_VARS}"
)

@pytest.fixture
def oci_client():
    namespace = os.getenv("OCI_NAMESPACE")
    region = os.getenv("OCI_REGION")
    endpoint_url = f"https://{namespace}.compat.objectstorage.{region}.oraclecloud.com"
    
    # Configuración base: forzamos a que firme el payload completo
    # Esto evita que boto3 use 'Transfer-Encoding: chunked' que OCI no soporta
    config_kwargs = {
        "signature_version": "s3v4",
        "retries": {"max_attempts": 3, "mode": "standard"},
        "s3": {"payload_signing_enabled": True}
    }
    
    try:
        config = Config(
            **config_kwargs,
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required"
        )
    except TypeError:
        # Fallback si botocore es antiguo y no reconoce los nuevos parámetros de checksum
        config = Config(**config_kwargs)

    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=os.getenv("OCI_ACCESS_KEY"),
        aws_secret_access_key=os.getenv("OCI_SECRET_KEY"),
        region_name=region,
        config=config,
    )

@pytest.fixture
def bucket_name():
    return os.getenv("OCI_BUCKET_NAME")

def test_oci_put_object_bytes(oci_client, bucket_name):
    """
    Test de integración: Sube un archivo usando bytes directamente.
    Verifica que el ContentLength se maneje correctamente.
    """
    test_content = b"Contenido de prueba via pytest (bytes)"
    object_name = f"test_pytest_{uuid.uuid4()}.txt"
    size = len(test_content)

    print(f"\nSubiendo {size} bytes a {object_name}...")

    try:
        response = oci_client.put_object(
            Bucket=bucket_name,
            Key=object_name,
            Body=test_content,
            ContentLength=size,
            ContentType="text/plain"
        )
        assert response["ResponseMetadata"]["HTTPStatusCode"] == 200
        print(f"✅ Upload exitoso")

        # Limpieza
        oci_client.delete_object(Bucket=bucket_name, Key=object_name)
        print(f"✅ Cleanup exitoso")
    except ClientError as e:
        pytest.fail(f"OCI PutObject falló con ClientError: {e}")

def test_oci_put_object_stream(oci_client, bucket_name):
    """
    Test de integración: Sube un archivo usando un stream (BytesIO).
    """
    test_data = b"Contenido de prueba via pytest (stream)"
    test_stream = io.BytesIO(test_data)
    object_name = f"test_pytest_stream_{uuid.uuid4()}.txt"
    size = len(test_data)

    print(f"\nSubiendo stream de {size} bytes a {object_name}...")

    try:
        # Importante: OCI requiere ContentLength explícito incluso para streams
        response = oci_client.put_object(
            Bucket=bucket_name,
            Key=object_name,
            Body=test_stream,
            ContentLength=size,
            ContentType="text/plain"
        )
        assert response["ResponseMetadata"]["HTTPStatusCode"] == 200
        print(f"✅ Upload stream exitoso")

        # Limpieza
        oci_client.delete_object(Bucket=bucket_name, Key=object_name)
    except ClientError as e:
        pytest.fail(f"OCI PutObject (stream) falló con ClientError: {e}")
