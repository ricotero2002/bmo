import boto3
import os
import io
import logging
from botocore.config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_upload_fileobj():
    endpoint = os.getenv("LAKEHOUSE_S3_ENDPOINT")
    key = os.getenv("OCI_ACCESS_KEY")
    secret = os.getenv("OCI_SECRET_KEY")
    
    s3 = boto3.client(
        's3',
        endpoint_url=endpoint,
        aws_access_key_id=key,
        aws_secret_access_key=secret,
        region_name='us-ashburn-1',
        config=Config(s3={'addressing_style': 'path'})
    )
    
    try:
        logger.info("Probando upload_fileobj...")
        f = io.BytesIO(b"hello from fileobj")
        s3.upload_fileobj(f, 'bronze', 'test_fileobj.txt')
        logger.info("✅ ¡ÉXITO!")
    except Exception as e:
        logger.error(f"❌ FALLÓ: {e}")

if __name__ == "__main__":
    test_upload_fileobj()
