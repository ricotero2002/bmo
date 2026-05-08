import pandas as pd
import os
import fsspec
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_oracle_put_file():
    endpoint = os.getenv("LAKEHOUSE_S3_ENDPOINT")
    key = os.getenv("OCI_ACCESS_KEY")
    secret = os.getenv("OCI_SECRET_KEY")
    
    storage_options = {
        "key": key,
        "secret": secret,
        "client_kwargs": {
            "endpoint_url": endpoint,
            "region_name": "us-ashburn-1"
        },
        "config_kwargs": {
            "s3": {"addressing_style": "path"},
            "signature_version": "s3v4"
        }
    }
    
    logger.info(f"Probando put_file con archivo local: {endpoint}")
    
    df = pd.DataFrame({"test": [1, 2, 3]})
    local_path = "/tmp/test_local.parquet"
    df.to_parquet(local_path, index=False)
    
    fs = fsspec.filesystem("s3", **storage_options)
    remote_path = "s3://bmo-documents/test_put_file.parquet"
    
    try:
        fs.put_file(local_path, remote_path)
        logger.info("✅ ¡ÉXITO! Archivo guardado usando put_file.")
        # Verificar
        df_read = pd.read_parquet(remote_path, storage_options=storage_options)
        logger.info(f"✅ Leído: \n{df_read}")
    except Exception as e:
        logger.error(f"❌ FALLÓ: {e}")
    finally:
        if os.path.exists(local_path):
            os.remove(local_path)

if __name__ == "__main__":
    test_oracle_put_file()
