import os
from src.providers.cache.redis_cache import RedisCache
from src.providers.cache.dynamodb_cache import DynamoDBCache


class CacheFactory:
    """
    Fábrica de caché:
      - local / staging → Redis (via RedisCache)
      - producción      → DynamoDB (via DynamoDBCache, free tier + TTL nativo)
    """

    @staticmethod
    def get_cache():
        env = os.getenv("APP_ENV", "local")
        '''
        if env == "production":
            table_name = os.getenv("AWS_DYNAMODB_TABLE_CACHE", "bmo-cache")
            region = os.getenv("AWS_REGION", "us-east-1")
            return DynamoDBCache(table_name=table_name, region=region)
        '''
        # Local/staging: Redis
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        return RedisCache(redis_url)
