from abc import ABC, abstractmethod
from typing import BinaryIO, Optional

class StorageProvider(ABC):
    @abstractmethod
    def upload_file(self, file_data: BinaryIO, object_name: str, bucket_name: Optional[str] = None) -> str:
        """Uploads a file to the storage provider. Returns the file path/URL."""
        pass

    @abstractmethod
    def download_file(self, object_name: str, bucket_name: Optional[str] = None) -> BinaryIO:
        """Downloads a file from the storage provider."""
        pass

    @abstractmethod
    def delete_file(self, object_name: str, bucket_name: Optional[str] = None) -> bool:
        """Deletes a file from the storage provider."""
        pass

    @abstractmethod
    def get_file_url(self, object_name: str, bucket_name: Optional[str] = None) -> str:
        """Returns a temporary/public URL for the file."""
        pass
