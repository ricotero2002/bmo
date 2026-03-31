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
    Construye la URL de la DB usando el proveedor del backend,
    soportando Oracle y Postgres de forma transparente.
    """
    from src.providers.database.core import get_database_url_and_args
    db_url, _ = get_database_url_and_args()
    return db_url


def include_object(obj, name, type_, reflected, compare_to):
    """
    Filtro para ignorar tablas de infraestructura externa (como LangGraph)
    en el autogenerate de Alembic.
    """
    if type_ == "table":
        # Ignorar tablas de checkpoints de LangGraph
        if name.startswith("checkpoint_"):
            return False
        # Ignorar tabla de migración de Alembic (por seguridad redundante)
        if name == "alembic_version":
            return False
    return True


def run_migrations_offline() -> None:
    """
    Modo 'offline': genera el SQL sin conectarse a la DB.
    Útil para revisar las migraciones antes de aplicarlas.
    """
    from src.providers.database.core import get_database_url_and_args
    url, connect_args = get_database_url_and_args()
    
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Modo 'online': se conecta a la DB y aplica las migraciones directamente.
    """
    from src.providers.database.core import get_engine
    
    connectable = get_engine()

    with connectable.connect() as connection:
        context.configure(
            connection=connection, 
            target_metadata=target_metadata,
            include_object=include_object
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
