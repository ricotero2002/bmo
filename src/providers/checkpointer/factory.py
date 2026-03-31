import os
from contextlib import asynccontextmanager
import logging
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

logger = logging.getLogger(__name__)

class CheckpointerFactory:
    """
    Fábrica del checkpointer de LangGraph.
    """

    @staticmethod
    @asynccontextmanager
    async def get_checkpointer():
        env = os.getenv("APP_ENV", "local")

        if env == "production":
            # Producción — PostgreSQL administrado (Aiven)
            conn_string = os.getenv("AIVEN_PG_URI")
            if not conn_string:
                raise ValueError("❌ Faltan las credenciales: AIVEN_PG_URI no está definido.")

            logger.info("🔌 Conectando a Aiven PostgreSQL Checkpointer...")
            
            # AsyncPostgresSaver maneja el sslmode=require automáticamente si está en la URI
            async with AsyncPostgresSaver.from_conn_string(conn_string) as saver:
                try:
                    logger.info("📡 Ejecutando saver.setup()...")
                    import psycopg
                    try:
                        await saver.setup()
                    except (psycopg.errors.UniqueViolation, psycopg.errors.DuplicateObject) as e:
                        logger.warning(f"⚠️ Migración concurrente ignorada en setup: {e}")
                    
                    logger.info("✅ Aiven PostgreSQL Checkpointer listo.")
                    yield saver
                except Exception as e:
                    logger.error(f"❌ ERROR configurando el checkpointer de Aiven: {str(e)}")
                    raise

        else:
            # Desarrollo local — PostgreSQL vía Docker Compose
            user = os.getenv("POSTGRES_USER", "postgres")
            password = os.getenv("POSTGRES_PASSWORD", "postgres")
            db = os.getenv("POSTGRES_DB", "postgres")
            host = os.getenv("DB_HOST", "db")
            port = os.getenv("DB_PORT", "5432")
            conn_string = f"postgresql://{user}:{password}@{host}:{port}/{db}"

            async with AsyncPostgresSaver.from_conn_string(conn_string) as saver:
                try:
                    import psycopg
                    await saver.setup()
                except (psycopg.errors.UniqueViolation, psycopg.errors.DuplicateObject) as e:
                    logger.warning(f"⚠️ Migración concurrente local ignorada en setup: {e}")
                except Exception as e:
                    logger.warning(f"⚠️ Setup error: {e}")
                yield saver
