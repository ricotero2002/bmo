import os
from contextlib import asynccontextmanager


class CheckpointerFactory:
    """
    Fábrica del checkpointer de LangGraph.

    - local      → AsyncPostgresSaver apuntando al PostgreSQL de Docker Compose
    - production → AsyncOracleSaver apuntando a Oracle Autonomous Database (Always Free)
                   Requiere el paquete: pip install langgraph-checkpoint-oracle oracledb

    El checkpointer guarda el estado del grafo de LangGraph entre invocaciones,
    permitiendo que el agente "recuerde" conversaciones pasadas.

    Variables de entorno (producción):
      DB_USER, DB_PASSWORD, DB_HOST, DB_SERVICE_NAME, DB_PORT (default: 1521, TLS)

    REQUISITO OCI: en tu instancia de Autonomous DB, ve a DB Connection y desactiva
    "Require Mutual TLS (mTLS) Authentication" para permitir conexiones TLS sin wallet.
    """

    @staticmethod
    @asynccontextmanager
    async def get_checkpointer():
        env = os.getenv("APP_ENV", "local")

        if env == "production":
            # Oracle Autonomous DB — TLS sin wallet (puerto 1521)
            import ssl
            import oracledb
            from langgraph.checkpoint.oracle.aio import AsyncOracleSaver

            ssl_ctx = ssl.create_default_context()
            
            # 1. Instanciar el objeto vacío (el constructor no acepta 'dsn')
            params = oracledb.ConnectParams()
            
            # 2. Parsear el DSN usando el método oficial de la librería
            dsn_env = os.getenv("DB_DSN")
            if dsn_env:
                params.parse_connect_string(dsn_env)
            else:
                # Si vienen variables separadas (K8s), armamos el string forzando TCPS y lo parseamos
                constructed_dsn = oracledb.makedsn(
                    host=os.getenv("DB_HOST"),
                    port=int(os.getenv("DB_PORT", "1521")),
                    service_name=os.getenv("DB_SERVICE_NAME"),
                    protocol="tcps"
                )
                params.parse_connect_string(constructed_dsn)
            
            # 3. Inyectar credenciales y el contexto SSL usando el método .set()
            params.set(
                user=os.getenv("DB_USER"),
                password=os.getenv("DB_PASSWORD"),
                ssl_context=ssl_ctx
            )

            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"🔌 Conectando a Oracle Checkpointer (User: {os.getenv('DB_USER')})...")
            
            import asyncio
            saver_ctx = AsyncOracleSaver.from_conn_params(params)
            try:
                # 1. Conexión y Setup (Bajo timeout de 60s)
                try:
                    async with asyncio.timeout(60):
                        saver = await saver_ctx.__aenter__()
                        logger.info("📡 Ejecutando saver.setup()...")
                        await saver.setup()
                        logger.info("✅ Oracle Checkpointer listo.")
                except asyncio.TimeoutError:
                    logger.error("❌ TIMEOUT: No se pudo conectar/configurar Oracle en 60s.")
                    logger.error(f"   Host: {params.host}, Port: {params.port}, Service: {params.service_name}")
                    raise RuntimeError("Oracle connection timed out during startup")
                
                # 2. Mantener vivo el objeto para el resto de la app (Fuera del timeout)
                yield saver

            except Exception as e:
                logger.error(f"❌ ERROR inesperado en Oracle: {str(e)}")
                raise
            finally:
                # 3. Limpieza al cerrar la app
                await saver_ctx.__aexit__(None, None, None)
        else:
            # Desarrollo local — PostgreSQL vía Docker Compose
            user = os.getenv("POSTGRES_USER", "postgres")
            password = os.getenv("POSTGRES_PASSWORD", "postgres")
            db = os.getenv("POSTGRES_DB", "postgres")
            host = os.getenv("DB_HOST", "db")
            port = os.getenv("DB_PORT", "5432")
            conn_string = f"postgresql://{user}:{password}@{host}:{port}/{db}"

            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
            async with AsyncPostgresSaver.from_conn_string(conn_string) as saver:
                await saver.setup()
                yield saver
