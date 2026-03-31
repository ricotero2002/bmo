# Guía de Migraciones de Base de Datos

Con la implementación de la Fase 6, hemos centralizado la lógica de conexión y automatizado las migraciones para que funcionen tanto en **PostgreSQL (Local)** como en **Oracle (Cloud/Remote)** de forma transparente.

## Script de Automatización: `migrate_db.py`

Hemos creado el script `scripts/migrate_db.py` para evitar configurar manualmente variables de entorno o comandos complejos de Alembic.

### 1. Actualizar Base de Datos (Upgrade)

Este comando aplica todas las migraciones pendientes al "head" (la última versión).

#### Para Postgres (Local):
```bash
python scripts/migrate_db.py upgrade postgres
```
*(Es el valor por defecto, así que `python scripts/migrate_db.py` también funciona).*

#### Para Oracle (Cloud):
```bash
python scripts/migrate_db.py upgrade oracle
```
> [!IMPORTANT]
> Para Oracle, el script se encarga de configurar internamente `DB_TYPE=oracle`, lo que activa la conexión via TCPS/SSL y usa las variables `DB_USER`, `DB_PASSWORD`, `DB_DSN` (o `DB_HOST`/`DB_SERVICE_NAME`) que ya tienes configuradas.

---

### 2. Generar Nuevas Migraciones (Autogenerate)

Si realizas cambios en los modelos de SQLAlchemy (`src/providers/database/models.py`), debes generar una nueva versión de migración.

#### Ejemplo para Postgres:
```bash
python scripts/migrate_db.py generate postgres "Descripción del cambio"
```

#### Ejemplo para Oracle:
```bash
python scripts/migrate_db.py generate oracle "Descripción del cambio"
```

---

## Cómo funciona por detrás

1.  **`src/providers/database/core.py`**: Este módulo detecta si la base de datos es Oracle o Postgres basándose en el parámetro o variables de entorno. Configura los `connect_args` específicos (como el contexto SSL para Oracle).
2.  **`alembic/env.py`**: Ahora importa la configuración desde `core.py`, asegurando que Alembic "hable" el mismo idioma que el resto de la aplicación.
3.  **Idempotencia**: El script asegura que las tablas se creen o actualicen sin borrar datos existentes, siguiendo el historial de versiones en la carpeta `alembic/versions`.

---

## Solución de Problemas

*   **Error de conexión en Oracle**: Asegúrate de tener las variables de entorno de Oracle cargadas en tu terminal antes de correr el script.
*   **pytest no encontrado**: Recuerda siempre activar tu entorno virtual antes de ejecutar comandos:
    ```bash
    .venv\Scripts\activate
    ```
