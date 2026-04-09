import os
import logging
from contextlib import asynccontextmanager
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

logger = logging.getLogger(__name__)

# Variable global para mantener el pool vivo
_pg_pool = None

class CheckpointerFactory:
    """
    Fábrica del checkpointer de LangGraph con soporte para Connection Pooling.
    """

    @staticmethod
    async def _get_pool(conn_string: str):
        global _pg_pool
        if _pg_pool is None:
            logger.info("Initializing AsyncConnectionPool for PostgreSQL Checkpointer...")
            _pg_pool = AsyncConnectionPool(
                conninfo=conn_string,
                max_size=20,
                min_size=2,
                open=False,  # Don't open in constructor (deprecated)
                # autocommit=True is often required for LangGraph's saver
                kwargs={"autocommit": True, "prepare_threshold": 0},
            )
            await _pg_pool.open()
        return _pg_pool

    @staticmethod
    @asynccontextmanager
    async def get_checkpointer():
        env = os.getenv("APP_ENV", "local")
        
        if env == "production":
            conn_string = os.getenv("AIVEN_PG_URI")
            if not conn_string:
                raise ValueError("❌ missing credentials: AIVEN_PG_URI is not defined.")
            logger.info("🔌 Connecting to Aiven PostgreSQL Checkpointer (with pool)...")
        else:
            user = os.getenv("POSTGRES_USER", "postgres")
            password = os.getenv("POSTGRES_PASSWORD", "postgres")
            db = os.getenv("POSTGRES_DB", "postgres")
            host = os.getenv("DB_HOST", "db")
            port = os.getenv("DB_PORT", "5432")
            conn_string = f"postgresql://{user}:{password}@{host}:{port}/{db}"
            logger.info(f"🔌 Connecting to Local PostgreSQL Checkpointer (with pool) at {host}...")

        pool = await CheckpointerFactory._get_pool(conn_string)
        
        # AsyncPostgresSaver accepts the pool directly
        saver = AsyncPostgresSaver(pool)
        try:
            logger.info("📡 Running saver.setup()...")
            import psycopg
            try:
                await saver.setup()
            except (psycopg.errors.UniqueViolation, psycopg.errors.DuplicateObject) as e:
                logger.warning(f"⚠️ Concurrent migration ignored in setup: {e}")
            
            logger.info("✅ PostgreSQL Checkpointer ready.")
            yield saver
        except Exception as e:
            logger.error(f"❌ ERROR configuring checkpointer: {str(e)}")
            raise

    @staticmethod
    async def close_pool():
        global _pg_pool
        if _pg_pool is not None:
            logger.info("Closing PostgreSQL Checkpointer pool...")
            await _pg_pool.close()
            _pg_pool = None
