import io
import os
import logging
from typing import BinaryIO, Optional, Any
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from src.providers.storage.base import StorageProvider

logger = logging.getLogger(__name__)


class OCIStorageProvider(StorageProvider):
    """
    Proveedor de almacenamiento usando Oracle Object Storage via la API S3-compatible.

    Reusa el cliente boto3 apuntando al endpoint regional de OCI:
      https://{OCI_NAMESPACE}.compat.objectstorage.{OCI_REGION}.oraclecloud.com

    Variables de entorno requeridas:
      OCI_NAMESPACE    — Object Storage namespace de tu tenancy (ver OCI Console → Object Storage)
      OCI_REGION       — Región de OCI, ej. "us-ashburn-1"
      OCI_BUCKET_NAME  — Nombre del bucket ya creado en OCI
      OCI_ACCESS_KEY   — Access Key ID generado en OCI Console (Customer Secret Keys)
      OCI_SECRET_KEY   — Secret Key correspondiente

    Dependencias:
      pip install boto3
    """

    def __init__(self):
        namespace = os.getenv("OCI_NAMESPACE")
        region = os.getenv("OCI_REGION")
        access_key = os.getenv("OCI_ACCESS_KEY")
        secret_key = os.getenv("OCI_SECRET_KEY")
        self.bucket_name = os.getenv("OCI_BUCKET_NAME")

        if not all([namespace, region, access_key, secret_key, self.bucket_name]):
            raise ValueError(
                "Faltan variables de entorno de OCI: "
                "OCI_NAMESPACE, OCI_REGION, OCI_ACCESS_KEY, OCI_SECRET_KEY, OCI_BUCKET_NAME"
            )

        self.endpoint_url = (
            f"https://{namespace}.compat.objectstorage.{region}.oraclecloud.com"
        )

        # OCI requiere estrictamente S3v4 para autenticación y payload firmado.
        # Forzar payload_signing_enabled evita que boto3 use 'Transfer-Encoding: chunked'
        # que OCI no soporta en PutObject.
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
            # Fallback si botocore es antiguo
            config = Config(**config_kwargs)

        self.client = boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=config,
        )
        logger.info(
            f"OCIStorageProvider iniciado — endpoint: {self.endpoint_url}, "
            f"bucket: {self.bucket_name}"
        )

    def upload_file(self, file_data: Any, object_name: str, bucket_name: Optional[str] = None) -> str:
        """
        Sube un archivo (bytes o stream) al bucket de OCI.
        """
        bucket = bucket_name or self.bucket_name
        
        # 1. Determinar el contenido (bytes) y el tamaño
        # OCI requiere Content-Length explícito para PutObject
        if isinstance(file_data, bytes):
            file_bytes = file_data
            size = len(file_bytes)
        else:
            # Asumimos que es un file-like object (BinaryIO)
            # Nos aseguramos de leerlo desde el principio
            if hasattr(file_data, "seek"):
                file_data.seek(0)
            file_bytes = file_data.read()
            size = len(file_bytes)
        
        logger.warning(f"--- DEBUG OCI: {object_name} (bytes size: {size}) ---")

        import mimetypes
        content_type, _ = mimetypes.guess_type(object_name)
        if not content_type:
            content_type = "application/octet-stream"

        # 2. Ejecutar el PutObject con ContentLength obligatorio para OCI
        try:
            self.client.put_object(
                Bucket=bucket,
                Key=object_name,
                Body=file_bytes,
                ContentLength=size,
                ContentType=content_type,
                ContentDisposition="inline"
            )
            logger.warning(f"Éxito: oci://{bucket}/{object_name} ({size} bytes) [{content_type}]")
        except ClientError as e:
            logger.error(f"Fallo PutObject en OCI: {e}")
            raise

        return object_name

    def download_file(self, object_name: str, bucket_name: Optional[str] = None) -> BinaryIO:
        bucket = bucket_name or self.bucket_name
        buffer = io.BytesIO()
        self.client.download_fileobj(bucket, object_name, buffer)
        buffer.seek(0)
        return buffer

    def delete_file(self, object_name: str, bucket_name: Optional[str] = None) -> bool:
        bucket = bucket_name or self.bucket_name
        self.client.delete_object(Bucket=bucket, Key=object_name)
        logger.info(f"Archivo eliminado: oci://{bucket}/{object_name}")
        return True

    def get_file_url(self, object_name: str, bucket_name: Optional[str] = None) -> str:
        bucket = bucket_name or self.bucket_name
        # URL prefirmada válida por 1 hora
        return self.client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": bucket, 
                "Key": object_name,
                "ResponseContentDisposition": "inline"
            },
            ExpiresIn=3600,
        )
