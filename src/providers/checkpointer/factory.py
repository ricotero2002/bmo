import os
from contextlib import asynccontextmanager


class CheckpointerFactory:
    """
    Fábrica del checkpointer de LangGraph.

    - local     → AsyncPostgresSaver apuntando al PostgreSQL de Docker
    - production → AsyncPostgresSaver apuntando a Amazon RDS for PostgreSQL
                   (mismo código, distinto DB_HOST en las variables de entorno)

    El checkpointer guarda el estado del grafo de LangGraph entre invocaciones,
    permitiendo que el agente "recuerde" conversaciones pasadas.
    """

    @staticmethod
    def get_conn_string() -> str:
        user = os.getenv("POSTGRES_USER", "postgres")
        password = os.getenv("POSTGRES_PASSWORD", "postgres")
        db = os.getenv("POSTGRES_DB", "postgres")
        port = os.getenv("DB_PORT", "5432")

        env = os.getenv("APP_ENV", "local")
        if env == "production":
            # En producción, DB_HOST es el endpoint de Amazon RDS for PostgreSQL
            host = os.getenv("DB_HOST", "localhost")
        else:
            # En local/Docker, el host es el nombre del servicio en docker-compose
            host = os.getenv("DB_HOST", "db")

        return f"postgresql://{user}:{password}@{host}:{port}/{db}"

    @staticmethod
    @asynccontextmanager
    async def get_checkpointer():
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        async with AsyncPostgresSaver.from_conn_string(CheckpointerFactory.get_conn_string()) as saver:
            await saver.setup()
            yield saver

