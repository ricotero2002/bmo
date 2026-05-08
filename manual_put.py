import requests
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_manual_put():
    endpoint = os.getenv("LAKEHOUSE_S3_ENDPOINT")
    # Intentar un PUT crudo (sin firmar, solo para ver si el error cambia)
    url = f"{endpoint}/bronze/test_raw.txt"
    logger.info(f"Probando PUT crudo a {url}")
    
    headers = {"Content-Length": "10"}
    try:
        r = requests.put(url, data="1234567890", headers=headers, verify=False)
        logger.info(f"Status: {r.status_code}")
        logger.info(f"Response: {r.text}")
    except Exception as e:
        logger.error(f"Error: {e}")

if __name__ == "__main__":
    test_manual_put()
