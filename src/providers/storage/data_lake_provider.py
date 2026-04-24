import os
import pandas as pd
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DataLakeProvider:
    """
    Abstracción para el almacenamiento de objetos (MinIO, S3, Oracle Object Storage, etc.).
    Permite guardar DataFrames en formato Parquet de forma transparente.
    """
    def __init__(self):
        # Configuraciones desde variables de entorno para facilitar el cambio de proveedor
        self.endpoint = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
        self.key = os.getenv("MINIO_ROOT_USER", "lakehouse")
        self.secret = os.getenv("MINIO_ROOT_PASSWORD", "lakehouse123")
        
        # Opciones de almacenamiento para s3fs
        self.storage_options = {
            "key": self.key,
            "secret": self.secret,
            "client_kwargs": {"endpoint_url": self.endpoint}
        }
        
        logger.info(f"DataLakeProvider inicializado con endpoint: {self.endpoint}")

    def write_parquet_chunk(self, df: pd.DataFrame, zone: str, table_name: str, partition_date: str, chunk_idx: int):
        """
        Escribe un DataFrame como un archivo Parquet en una ruta particionada por fecha.
        Ej: s3://bronze/langsmith_raw/date=2026-04-23/chunk_0.parquet
        """
        base_path = f"s3://{zone}/{table_name}/date={partition_date}"
        file_path = f"{base_path}/chunk_{chunk_idx}.parquet"
        
        logger.info(f"Guardando chunk {chunk_idx} en {file_path} ({len(df)} filas)")
        
        df.to_parquet(file_path, storage_options=self.storage_options, index=False)
        return file_path

    def list_partition_files(self, zone: str, table_name: str, partition_date: str):
        """Lista los archivos en una partición específica."""
        path = f"s3://{zone}/{table_name}/date={partition_date}"
        # Nota: Aquí se podría usar s3fs directamente para listar si fuera necesario
        return path
