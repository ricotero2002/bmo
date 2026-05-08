import boto3
import os
import io
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_boto3_write():
    endpoint = os.getenv("LAKEHOUSE_S3_ENDPOINT")
    key = os.getenv("OCI_ACCESS_KEY")
    secret = os.getenv("OCI_SECRET_KEY")
    
    logger.info(f"Probando escritura con BOTO3 en OCI: {endpoint}")
    
    from botocore.config import Config
    
    s3 = boto3.client(
        's3',
        endpoint_url=endpoint,
        aws_access_key_id=key,
        aws_secret_access_key=secret,
        region_name='us-ashburn-1',
        config=Config(s3={'addressing_style': 'path'})
    )
    
    body = b"test data from boto3"
    bucket = "bronze"
    key_name = "test_boto3.txt"
    
    try:
        logger.info(f"Enviando PutObject a {bucket}/{key_name}...")
        response = s3.put_object(
            Bucket=bucket,
            Key=key_name,
            Body=body,
            ContentLength=len(body) # Forzando ContentLength
        )
        logger.info(f"✅ ÉXITO: {response}")
    except Exception as e:
        logger.error(f"❌ FALLÓ Boto3: {e}")

if __name__ == "__main__":
    test_boto3_write()
