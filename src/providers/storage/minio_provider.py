import io
from typing import BinaryIO, Optional
from minio import Minio
from src.core.config import settings
from src.providers.storage.base import StorageProvider

class MinioStorageProvider(StorageProvider):
    def __init__(self):
        self.client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE
        )
        self.bucket_name = settings.MINIO_BUCKET_NAME
        self._ensure_bucket_exists()

    def _ensure_bucket_exists(self):
        if not self.client.bucket_exists(self.bucket_name):
            self.client.make_bucket(self.bucket_name)

    def upload_file(self, file_data: BinaryIO, object_name: str, bucket_name: Optional[str] = None) -> str:
        bucket = bucket_name or self.bucket_name
        
        # Ensure we are at the start of the file
        file_data.seek(0, io.SEEK_END)
        size = file_data.tell()
        file_data.seek(0)
        
        self.client.put_object(
            bucket,
            object_name,
            file_data,
            length=size
        )
        return object_name

    def download_file(self, object_name: str, bucket_name: Optional[str] = None) -> BinaryIO:
        bucket = bucket_name or self.bucket_name
        response = self.client.get_object(bucket, object_name)
        return io.BytesIO(response.read())

    def delete_file(self, object_name: str, bucket_name: Optional[str] = None) -> bool:
        bucket = bucket_name or self.bucket_name
        self.client.remove_object(bucket, object_name)
        return True

    def get_file_url(self, object_name: str, bucket_name: Optional[str] = None) -> str:
        bucket = bucket_name or self.bucket_name
        # Generates a presigned URL valid for 1 hour
        return self.client.presigned_get_object(bucket, object_name)
