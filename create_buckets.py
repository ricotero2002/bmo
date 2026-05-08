import boto3
import os
import logging
from botocore.config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_oci_buckets():
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
    
    for bucket in ["bronze", "silver", "gold", "warehouse"]:
        try:
            logger.info(f"Intentando crear bucket: {bucket}")
            s3.create_bucket(Bucket=bucket)
            logger.info(f"✅ Bucket {bucket} creado.")
        except Exception as e:
            logger.error(f"❌ No se pudo crear {bucket}: {e}")

if __name__ == "__main__":
    create_oci_buckets()
