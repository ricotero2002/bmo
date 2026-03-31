import os
import ssl
from sqlalchemy import create_engine

def get_database_url_and_args():
    """
    Detects if the environment is configured for Oracle or Postgres 
    and returns the SQLAlchemy URL and connection arguments.
    """
    db_type = os.getenv("DB_TYPE", "").lower()
    
    # If DB_TYPE is explicitly oracle, or if Oracle specific vars are present
    if db_type == "oracle" or os.getenv("DB_DSN") or os.getenv("DB_SERVICE_NAME"):
        user = os.getenv("DB_USER")
        password = os.getenv("DB_PASSWORD")
        dsn = os.getenv("DB_DSN")

        ssl_ctx = ssl.create_default_context()
        
        # Todo lo que pongas aquí se le pasa directo por debajo a oracledb.connect()
        connect_args = {"ssl_context": ssl_ctx}

        if dsn:
            # Si hay DSN, lo pasamos como argumento en lugar de ensuciar la URL
            db_url = f"oracle+oracledb://{user}:{password}@"
            connect_args["dsn"] = dsn
        else:
            host = os.getenv("DB_HOST", "localhost")
            port = os.getenv("DB_PORT", "1521")
            service_name = os.getenv("DB_SERVICE_NAME")
            db_url = f"oracle+oracledb://{user}:{password}@{host}:{port}/?service_name={service_name}"
            # TRUCO VITAL: Le exigimos a SQLAlchemy que use TCPS para Oracle Cloud
            connect_args["protocol"] = "tcps"
            
        return db_url, connect_args

    else:
        # Configuración por defecto para Postgres Local
        user = os.getenv("POSTGRES_USER", "user")
        password = os.getenv("POSTGRES_PASSWORD", "password")
        host = os.getenv("DB_HOST", "localhost")
        port = os.getenv("DB_PORT", "5432")
        db = os.getenv("POSTGRES_DB", "record_manager")
        
        db_url = f"postgresql://{user}:{password}@{host}:{port}/{db}"
        return db_url, {}

def get_engine(echo=False, pool_timeout=10, pool_pre_ping=True):
    """
    Creates and returns a SQLAlchemy Engine configured for the correct DB Provider.
    """
    db_url, connect_args = get_database_url_and_args()
    return create_engine(
        db_url,
        echo=echo,
        connect_args=connect_args,
        pool_timeout=pool_timeout,
        pool_pre_ping=pool_pre_ping
    )
