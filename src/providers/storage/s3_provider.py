import io
import boto3
import logging
from typing import BinaryIO, Optional
from src.providers.storage.base import StorageProvider

logger = logging.getLogger(__name__)


class S3StorageProvider(StorageProvider):
    """Proveedor de almacenamiento usando Amazon S3. Misma interfaz que MinioStorageProvider."""

    def __init__(self, bucket_name: str, region: str):
        # boto3 toma AWS_ACCESS_KEY_ID y AWS_SECRET_ACCESS_KEY desde las variables de entorno
        # (o desde el IAM Role del contenedor en ECS, que es el modo recomendado en producción)
        self.bucket_name = bucket_name
        self.region = region
        self.client = boto3.client("s3", region_name=region)
        self._ensure_bucket_exists()

    def _ensure_bucket_exists(self):
        try:
            self.client.head_bucket(Bucket=self.bucket_name)
        except self.client.exceptions.ClientError as e:
            error_code = int(e.response["Error"]["Code"])
            if error_code == 404:
                logger.info(f"Bucket '{self.bucket_name}' no existe, creándolo...")
                if self.region == "us-east-1":
                    self.client.create_bucket(Bucket=self.bucket_name)
                else:
                    self.client.create_bucket(
                        Bucket=self.bucket_name,
                        CreateBucketConfiguration={"LocationConstraint": self.region},
                    )
            else:
                raise

    def upload_file(self, file_data: BinaryIO, object_name: str, bucket_name: Optional[str] = None) -> str:
        bucket = bucket_name or self.bucket_name
        file_data.seek(0)
        self.client.upload_fileobj(file_data, bucket, object_name)
        logger.info(f"Archivo subido a s3://{bucket}/{object_name}")
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
        return True

    def get_file_url(self, object_name: str, bucket_name: Optional[str] = None) -> str:
        bucket = bucket_name or self.bucket_name
        # URL prefirmada válida por 1 hora
        return self.client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": bucket, 
                "Key": object_name,
                "ResponseContentDisposition": "inline",
                "ResponseContentType": "text/plain" 
            },
            ExpiresIn=3600,
        )
