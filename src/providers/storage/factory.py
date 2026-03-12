from src.core.config import settings
from src.providers.storage.minio_provider import MinioStorageProvider

class StorageFactory:
    _instance = None

    @staticmethod
    def get_storage() -> MinioStorageProvider:
        if StorageFactory._instance is None:
            # We could add logic here for different providers later (e.g. S3Provider)
            StorageFactory._instance = MinioStorageProvider()
        return StorageFactory._instance
