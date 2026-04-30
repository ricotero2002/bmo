# 🚀 Fase 9: Implementación de Ingesta Masiva y Patrón Claim-Check

Este documento describe la solución técnica y los cambios implementados para cumplir con el diseño de ingesta masiva (Nervio del Agente) establecido en el plan original.

## Resumen de la Arquitectura Implementada

Se ha migrado el flujo de ingesta de archivos hacia un patrón **Claim-Check**, lo que permite separar la carga pesada de archivos en Storage (MinIO) del procesamiento orquestado por la API y Celery. Esto elimina cuellos de botella en el Backend y evita duplicaciones de archivos.

## Cambios Realizados

### 1. Base de Datos (Seguimiento de Estado)
- **Archivo Modificado:** `src/providers/database/models.py`
- **Cambios:**
  - Se añadió la tabla `IngestionSyncState` para llevar el control del **CDC (Change Data Capture)**.
  - Guarda atributos clave: `user_id`, `source_type` (ej. notion), `last_sync_at` y `status`.
- **Archivo Modificado:** `src/providers/database/status_provider.py`
- **Cambios:**
  - Se añadieron los métodos `update_sync_state` y `get_sync_state` para leer y escribir de forma segura y transaccional los tiempos de sincronización.

### 2. Orquestador (`IngestionOrchestrator`)
- **Archivo Modificado:** `src/service/orchestrator.py`
- **Cambios:**
  - Se modificó la firma de `orchestrate_ingestion` para recibir un argumento opcional `batch_id`.
  - Se habilitó explícitamente la lógica para ignorar la subida al Storage (MinIO) si no se provee `content` (bytes), pero sí se recibe el `object_name`. Esto permite que Airflow u otro servicio suba el archivo directamente al Storage y el orquestador se encargue solo de encolar en Celery y registrar en la Base de Datos.

### 3. Endpoints de la API
- **Archivo Modificado:** `src/schemas/fastapi.py`
- **Cambios:**
  - Se añadieron los esquemas `TriggerFile` y `TriggerIngestionRequest` para validar el payload de llamadas automatizadas.
- **Archivo Modificado:** `src/api/endpoints.py`
- **Cambios:**
  - Se creó el endpoint `POST /api/v1/ingest/trigger`.
  - Este endpoint recibe una lista de archivos que ya están subidos en MinIO. Delega individualmente cada archivo al `IngestionOrchestrator` usando el `batch_id` para agrupar lógicamente la carga, retornando un consolidado de éxitos/fallos de inmediato sin procesar en RAM.
  - Se modificó `POST /api/v1/ingest/batch` para funcionar bajo la misma lógica global de agrupamiento.
  - Se creó el endpoint `GET /api/v1/ingestion-status/batch/{batch_id}`. Este recurso expone un resumen global del lote (éxito/fallos, total de archivos) junto con un desglose interno detallando el estado de cada trabajo individual (`IngestionJob`) perteneciente a ese lote.

### 3.5. Rastreo Integral de Batch (Nuevo en DB)
- **Archivo Modificado:** `src/providers/database/models.py`
- **Cambios:** Se incluyó el modelo `IngestionBatch` para registrar metadatos de agrupamiento (cantidad de archivos, listado de `doc_ids` en JSON, listado de errores y status final de la pre-orquestación).
- **Archivo Modificado:** `src/providers/database/status_provider.py`
- **Cambios:**
  - `save_batch_info`: Registra o actualiza el modelo `IngestionBatch` una vez que la API encola el lote completo.
  - `get_batch_details`: Devuelve una estructura jerárquica con el estado general de lote, concatenando (vía un join lógico sobre `IngestionJob`) el detalle en tiempo real de cada archivo en Celery.

### 4. Automatización (Airflow DAG)
- **Archivo Modificado:** `data_tooling/airflow/dags/notion_sync.py`
- **Cambios:**
  - Se implementó un DAG robusto de producción utilizando el API TaskFlow.
  - Se utiliza **Dynamic Task Mapping (`.expand()`)** para paralelizar la sincronización: Airflow consulta al backend los usuarios a sincronizar y lanza dinámicamente un worker independiente por cada usuario. Esto previene sobrecargas (OOM) al no cargar la información de todos los usuarios en la memoria de una sola tarea.
  - Implementación estricta de paginación con la API de Notion (`next_cursor`), subiendo lotes (`batch`) de JSON a MinIO/OCI por partes.
  - Respeto a los límites de la API delegando a Airflow la extracción de a pocos en lugar de forzar a Apache Spark a hacer los Request.



1. ¿Cómo funciona el tema de los Workers con .expand()?
La función sync_notion_user.expand(target=targets) es lo que Airflow llama Dynamic Task Mapping. Funciona así:

La primera tarea (get_users_to_sync) se comunica con tu API y obtiene, supongamos, 50 usuarios que necesitan ser sincronizados.
Al pasarle esa lista al .expand(), Airflow clona dinámicamente la tarea sync_notion_user en 50 tareas independientes (sync_notion_user[0], sync_notion_user[1], ..., sync_notion_user[49]).
El scheduler de Airflow encola estas 50 tareas en Celery.
Si tienes configurados 10 workers de Airflow (o un CeleryExecutor con paralelismo alto), los workers tomarán usuarios en paralelo y procesarán sus datos de Notion al mismo tiempo. Si un usuario tiene un token inválido y falla, solo falla su tarea; los demás 49 usuarios se sincronizan sin problemas.
Esto te permite escalar de manera horizontal infinita agregando más workers a tu clúster.

### 5. Seguridad de Integraciones (Nueva Implementación)
- **Archivos Creados/Modificados:** `src/providers/database/models.py` y `src/api/integrations.py`.
- **Cambios:**
  - Se incorporó la tabla `UserIntegration` para persistir los identificadores (`database_id`) y tokens (`access_token`) de las integraciones de terceros.
  - **AES-256:** Los tokens no viajan ni se guardan en texto plano; SQLAlchemy (`sqlalchemy-utils`) encripta transparente las columnas en la DB con una llave simétrica (`DB_ENCRYPTION_KEY`).
  - Se definieron endpoints dedicados en `/api/internal/sync/notion/targets` para que Airflow lea las credenciales a procesar de forma segura, haciendo un JOIN interno con `IngestionSyncState` para determinar el vector CDC o Full Load de la cuenta.

## Cómo generar la llave de encriptación (`DB_ENCRYPTION_KEY`)
Para inicializar el sistema de integraciones, debes guardar una llave de 32 bytes (url-safe base64-encoded) en tu `.env`. Puedes generarla con Python:
```python
import os
import base64
print(base64.urlsafe_b64encode(os.urandom(32)).decode('utf-8'))
```

## Próximos Pasos (Opcional):
- Añadir comandos a Alembic (`alembic revision --autogenerate`) para asentar la nueva tabla `user_integrations` en la base de datos Oracle.
- Ejecutar el pipeline reconstruyendo las imágenes Docker.
