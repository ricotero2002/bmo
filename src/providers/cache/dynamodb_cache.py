import json
import time
import boto3
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class DynamoDBCache:
    """
    Caché usando DynamoDB como backend. Misma interfaz que RedisCache.
    La tabla DynamoDB debe tener:
      - Partition Key: 'cache_key' (String)
      - TTL attribute: 'expires_at' (Number) — activar TTL en la consola AWS sobre este campo
    """

    def __init__(self, table_name: str, region: str):
        # boto3 toma AWS_ACCESS_KEY_ID y AWS_SECRET_ACCESS_KEY de las variables de entorno
        self.table_name = table_name
        self.client = boto3.resource("dynamodb", region_name=region)
        self.table = self.client.Table(table_name)

    async def get(self, key: str) -> Optional[str]:
        try:
            response = self.table.get_item(Key={"cache_key": key})
            item = response.get("Item")
            if not item:
                return None
            # Verificar si el ítem expiró manualmente (por si el TTL de DynamoDB tarda en limpiar)
            if "expires_at" in item and item["expires_at"] < int(time.time()):
                return None
            return item.get("value")
        except Exception as e:
            logger.warning(f"DynamoDBCache.get error: {e}")
            return None

    async def set(self, key: str, value: str, ttl: int = 3600):
        try:
            self.table.put_item(
                Item={
                    "cache_key": key,
                    "value": value,
                    "expires_at": int(time.time()) + ttl,  # Timestamp Unix para TTL nativo de DynamoDB
                }
            )
        except Exception as e:
            logger.warning(f"DynamoDBCache.set error: {e}")
