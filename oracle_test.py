import pandas as pd
import io
import os
import fsspec
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mock de DataLakeProvider logic con el FIX
def test_oracle_write():
    endpoint = os.getenv("LAKEHOUSE_S3_ENDPOINT")
    key = os.getenv("OCI_ACCESS_KEY") or os.getenv("MINIO_ROOT_USER")
    secret = os.getenv("OCI_SECRET_KEY") or os.getenv("MINIO_ROOT_PASSWORD")
    
    storage_options = {
        "key": key,
        "secret": secret,
        "client_kwargs": {"endpoint_url": endpoint}
    }
    
    logger.info(f"Probando escritura en OCI: {endpoint}")
    
    # DataFrame de prueba
    df = pd.DataFrame({"test_id": [1, 2, 3], "data": ["hola", "oracle", "test"]})
    
    zone = "bronze"
    table_name = "test_connection"
    partition_date = "2026-05-08"
    file_path = f"s3://{zone}/{table_name}/date={partition_date}/test_file.parquet"
    
    try:
        # IMPLEMENTACIÓN DEL FIX
        logger.info("Usando buffer BytesIO (Fix Content-Length)...")
        buffer = io.BytesIO()
        df.to_parquet(buffer, index=False)
        buffer.seek(0)
        
        fs = fsspec.filesystem("s3", **storage_options)
        fs.pipe_file(file_path, buffer.getvalue())
            
        logger.info(f"✅ ÉXITO: Archivo guardado en {file_path}")
        
        # Verificar lectura
        logger.info("Verificando lectura...")
        df_read = pd.read_parquet(file_path, storage_options=storage_options)
        logger.info(f"✅ ÉXITO: Datos leídos correctamente:\n{df_read}")
        
    except Exception as e:
        logger.error(f"❌ FALLÓ la prueba: {e}")
        raise e

if __name__ == "__main__":
    test_oracle_write()
