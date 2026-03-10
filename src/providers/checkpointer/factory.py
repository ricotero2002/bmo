import os
from contextlib import asynccontextmanager
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.base import BaseCheckpointSaver

class CheckpointerFactory:
    @staticmethod
    def get_conn_string() -> str:
        # Usamos PostgreSQL para el guardado del grafo de LangGraph local y en producción
        # de acuerdo al feedback del usuario. No utilizamos sqlite ni memory.
        POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
        POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
        POSTGRES_DB = os.getenv("POSTGRES_DB", "postgres")
        DB_PORT = os.getenv("DB_PORT", "5432") 
        
        # psycopg soporta el string de conexión estándar de postgresql
        db_url = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@db:{DB_PORT}/{POSTGRES_DB}"
        
        return db_url

    @staticmethod
    @asynccontextmanager
    async def get_checkpointer():
        async with AsyncPostgresSaver.from_conn_string(CheckpointerFactory.get_conn_string()) as saver:
            await saver.setup()
            yield saver
