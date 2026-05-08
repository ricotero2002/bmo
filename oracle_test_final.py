import pandas as pd
import io
import os
import fsspec
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_oracle_final():
    endpoint = os.getenv("LAKEHOUSE_S3_ENDPOINT")
    key = os.getenv("OCI_ACCESS_KEY")
    secret = os.getenv("OCI_SECRET_KEY")
    
    logger.info(f"Probando FINAL con path-style y ContentLength manual: {endpoint}")
    
    df = pd.DataFrame({"test": [1, 2, 3]})
    buffer = io.BytesIO()
    df.to_parquet(buffer, index=False)
    data = buffer.getvalue()
    
    storage_options = {
        "key": key,
        "secret": secret,
        "client_kwargs": {"endpoint_url": endpoint},
        "config_kwargs": {"s3": {"addressing_style": "path"}},
        "s3_additional_kwargs": {"ContentLength": len(data)}
    }
    
    fs = fsspec.filesystem("s3", **storage_options)
    file_path = "s3://bronze/test_final.parquet"
    
    try:
        fs.pipe_file(file_path, data)
        logger.info("✅ ¡ÉXITO! Archivo guardado correctamente.")
    except Exception as e:
        logger.error(f"❌ FALLÓ: {e}")

if __name__ == "__main__":
    test_oracle_final()
