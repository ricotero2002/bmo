"""
Alembic env.py — Integración con los modelos SQLAlchemy del proyecto.

Cómo usar:
  1. Primera vez:
       alembic upgrade head

  2. Después de cambiar un modelo (agregar/quitar columna, etc.):
       alembic revision --autogenerate -m "descripcion breve del cambio"
       alembic upgrade head

  3. Rollback de la última migración:
       alembic downgrade -1

  4. Ver el estado actual:
       alembic current
       alembic history --verbose
"""
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# ── Aseguramos que el `src/` del proyecto esté en PYTHONPATH ─────────────────
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

# ── Importamos el Base de los modelos para que Alembic detecte los cambios ───
from src.providers.database.models import Base  # noqa: E402

# ── Configuración desde alembic.ini ──────────────────────────────────────────
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    """
    Construye la URL de la DB desde variables de entorno.
    Esto permite que el mismo alembic.ini funcione en local y en producción
    (RDS) sin cambiar el archivo.
    """
    user = os.getenv("POSTGRES_USER", "user")
    password = os.getenv("POSTGRES_PASSWORD", "password")
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "record_manager")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def run_migrations_offline() -> None:
    """
    Modo 'offline': genera el SQL sin conectarse a la DB.
    Útil para revisar las migraciones antes de aplicarlas.
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Modo 'online': se conecta a la DB y aplica las migraciones directamente.
    """
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
