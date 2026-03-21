import os
from src.core.config import settings


class StorageFactory:
    _instance = None

    @staticmethod
    def get_storage():
        if StorageFactory._instance is not None:
            return StorageFactory._instance

        env = os.getenv("APP_ENV", "local")

        if env == "production":
            from src.providers.storage.s3_provider import S3StorageProvider
            StorageFactory._instance = S3StorageProvider(
                bucket_name=settings.AWS_S3_BUCKET,
                region=settings.AWS_REGION,
            )
        else:
            from src.providers.storage.minio_provider import MinioStorageProvider
            StorageFactory._instance = MinioStorageProvider()

        return StorageFactory._instance
