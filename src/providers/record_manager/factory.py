import os
import ssl
import logging
import uuid
from typing import Sequence, Optional
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)


def _oracle_precreate_schema(engine) -> None:
    """
    Pre-crea las tablas internas de SQLRecordManager con tipos Oracle válidos.
    """
    ddl = """
        CREATE TABLE upsertion_record (
            uuid      VARCHAR2(255) NOT NULL,
            key       VARCHAR2(4000),
            namespace VARCHAR2(255) NOT NULL,
            group_id  VARCHAR2(255),
            updated_at FLOAT,
            PRIMARY KEY (uuid),
            CONSTRAINT uix_key_namespace UNIQUE (key, namespace)
        )
    """
    try:
        with engine.begin() as conn:
            conn.execute(text(ddl))
        logger.info("Tabla upsertion_record creada en Oracle.")
    except Exception as e:
        if "ORA-00955" in str(e) or "already exists" in str(e).lower():
            logger.debug("Tabla upsertion_record ya existe, continuando.")
        else:
            raise


class RecordManagerFactory:
    @staticmethod
    def get_manager():
        from langchain_classic.indexes import SQLRecordManager

        class OracleSQLRecordManager(SQLRecordManager):
            """
            Clase parcheada para soportar Oracle, ya que Langchain solo
            soporta nativamente Postgres, MySQL y SQLite.
            """

            def get_time(self) -> float:
                """Obtiene el epoch time actual directo desde la base de datos Oracle."""
                if self.engine.dialect.name == "oracle":
                    # SYS_EXTRACT_UTC nos da la hora sin timezone de Oracle, calculamos los segundos desde 1970
                    query = text("SELECT (CAST(SYS_EXTRACT_UTC(SYSTIMESTAMP) AS DATE) - TO_DATE('1970-01-01', 'YYYY-MM-DD')) * 86400 FROM DUAL")
                    with self.engine.connect() as conn:
                        res = conn.execute(query).scalar()
                        return float(res)
                return super().get_time()

            def update(
                self,
                keys: Sequence[str],
                *,
                group_ids: Optional[Sequence[Optional[str]]] = None,
                time_at_least: Optional[float] = None,
            ) -> None:
                """Realiza el UPSERT usando MERGE INTO (Estándar de Oracle)."""
                if self.engine.dialect.name != "oracle":
                    return super().update(keys, group_ids=group_ids, time_at_least=time_at_least)

                if not keys:
                    return
                
                group_ids = group_ids or ([None] * len(keys))
                if len(keys) != len(group_ids):
                    raise ValueError("La cantidad de keys no coincide con group_ids")

                update_time = self.get_time()
                if time_at_least and update_time < time_at_least:
                    update_time = time_at_least

                # Sentencia MERGE altamente optimizada para Oracle
                merge_stmt = text("""
                    MERGE INTO upsertion_record trg
                    USING (SELECT :uuid AS uuid, :key AS key, :namespace AS namespace, :group_id AS group_id, :updated_at AS updated_at FROM DUAL) src
                    ON (trg.key = src.key AND trg.namespace = src.namespace)
                    WHEN MATCHED THEN
                        UPDATE SET trg.uuid = src.uuid, trg.group_id = src.group_id, trg.updated_at = src.updated_at
                    WHEN NOT MATCHED THEN
                        INSERT (uuid, key, namespace, group_id, updated_at)
                        VALUES (src.uuid, src.key, src.namespace, src.group_id, src.updated_at)
                """)

                # Empaquetamos todo en una lista de diccionarios para hacer Batch Insert (executemany)
                records = [
                    {
                        "uuid": str(uuid.uuid4()),
                        "key": key,
                        "namespace": self.namespace,
                        "group_id": group_id,
                        "updated_at": float(update_time)
                    }
                    for key, group_id in zip(keys, group_ids)
                ]

                with self.engine.begin() as conn:
                    # BLINDAJE: Forzamos que la sesión no use paralelismo en esta transacción
                    # Esto evita el ORA-12838 incluso si la conexión es de tipo "_high"
                    conn.execute(text("ALTER SESSION DISABLE PARALLEL DML"))
                    
                    # Ejecutamos el Upsert
                    conn.execute(merge_stmt, records)

        # Oracle Autonomous DB (Always Free) — TLS sin wallet
        user = os.getenv("DB_USER")
        password = os.getenv("DB_PASSWORD")
        collection_name = os.getenv("COLLECTION_NAME", "bmo-documents")
        namespace = f"pinecone/{collection_name}"
        dsn = os.getenv("DB_DSN")

        if dsn:
            db_url = f"oracle+oracledb://{user}:{password}@/?dsn={dsn}"
        else:
            host = os.getenv("DB_HOST")
            service_name = os.getenv("DB_SERVICE_NAME")
            port = os.getenv("DB_PORT", "1521")
            db_url = f"oracle+oracledb://{user}:{password}@{host}:{port}/?service_name={service_name}"

        ssl_ctx = ssl.create_default_context()
        engine = create_engine(
            db_url, 
            echo=False, 
            connect_args={"ssl_context": ssl_ctx},
            pool_timeout=10,
            pool_pre_ping=True
        )

        # Pre-crear tabla y utilizar el manager que parcheamos arriba
        if dsn or "oracle" in db_url.lower():
            _oracle_precreate_schema(engine)
            manager = OracleSQLRecordManager(namespace, engine=engine)
        else:
            manager = SQLRecordManager(namespace, engine=engine)
            manager.create_schema()

        return manager
