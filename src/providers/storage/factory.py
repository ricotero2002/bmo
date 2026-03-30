import os


class StorageFactory:
    _instance = None

    @staticmethod
    def get_storage():
        if StorageFactory._instance is not None:
            return StorageFactory._instance

        env = os.getenv("APP_ENV", "local")

        if env == "production":
            # Producción: Oracle Object Storage via API S3-compatible
            from src.providers.storage.oci_storage_provider import OCIStorageProvider
            StorageFactory._instance = OCIStorageProvider()
        else:
            from src.providers.storage.minio_provider import MinioStorageProvider
            StorageFactory._instance = MinioStorageProvider()

        return StorageFactory._instance
