import boto3
import os
import logging
from botocore.config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def list_oci_buckets():
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
        response = s3.list_buckets()
        buckets = [b['Name'] for b in response['Buckets']]
        logger.info(f"Buckets encontrados: {buckets}")
    except Exception as e:
        logger.error(f"Error listando buckets: {e}")

if __name__ == "__main__":
    list_oci_buckets()
