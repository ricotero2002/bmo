# 🚀 Fase 9: Ingesta Masiva y CDC (Nervio del Agente)

Este documento detalla la arquitectura y el plan de ejecución para integrar el flujo de **Ingesta Masiva (Airflow)** con el procesamiento distribuido (**Celery**), utilizando un patrón **Claim-Check** sobre MinIO.

## 1. Objetivos de Arquitectura
1. **Unificación**: El mismo pipeline procesa una subida manual (UI) y una sincronización de Notion (Airflow).
2. **Escala**: Manejo de miles de notas mediante paginación (chunks) para no saturar la RAM.
3. **Eficiencia**: Eliminación del doble guardado en storage y remoción de Kafka para el transporte de archivos (usando MinIO como puente).

## 2. Componentes y Responsabilidades

### A. Capa de Datos (PostgreSQL)
Implementaremos una tabla de seguimiento para el **CDC (Change Data Capture)**:
- **Tabla**: `ingestion_sync_state`
- **Función**: Guardar el `last_sync_at` por cada `user_id` y `source` (notion/obsidian).

### B. Capa de Orquestación (`orchestrator.py`)
Refactorizaremos el método `orchestrate_ingestion` para:
- **Flujo Directo**: Si el archivo ya está en MinIO (Aca en realidad es en el proveedor, que actualmente es oracle) (vía Airflow), el orquestador **no vuelve a subirlo**. Hay que hacer que desde donde esta el grafo (data_tooling) se pueda acceder a el archivo de proveedores de src, por ahora la idea es usar el minio local pero usando el sistema de provedor para poder cambiar facilmente.
- **Despacho**: Encolar directamente en Celery enviando el `object_name` (path de S3).
- **Eliminación de Kafka**: El orquestador ya no enviará el contenido del archivo a Kafka, reduciendo latencia y consumo de red.

### C. Capa de Extracción (Airflow en `data_tooling`)
Crearemos DAGs especializados para el "Nervio del Agente":
- **Notion Sync DAG**:
    - Extrae de la API de Notion usando `updated_after` (desde DB).
    - Procesa en chunks de 100 registros.
    - Guarda JSONs crudos en `s3://raw-zone/notion/...` usando `MinIOProvider`.
    - Llama al endpoint de la API: `POST /api/v1/ingest/trigger`.1

## 3. Hoja de Ruta (Roadmap)

### Paso 1: Refactor del Orchestrator
- Modificar `orchestrate_ingestion` para que acepte un `object_name` pre-existente.
- Asegurar que `process_document_task` de Celery sea la única fuente de verdad para la vectorización.

### Paso 2: Endpoint de Trigger
- Crear `POST /api/v1/ingest/trigger` en `src/api/endpoints.py`.
- Este endpoint permitirá a Airflow notificar al sistema que hay nuevos datos listos en el storage.

### Paso 3: DAG de Notion (CDC)
- Implementar la lógica de paginación de Notion en `data_tooling/airflow/dags`.
- Configurar el uso de secretos (`.env`) para la clave de integración.

### Paso 4: Limpieza de Infraestructura
- Desactivar `kafka_consumer.py` para el tópico de documentos, manteniendo Kafka solo para eventos de telemetría o logs ligeros.

## 4. Flujo de Control (Claim-Check)
1. **Airflow** descarga de Notion -> Guarda en **MinIO** -> Envía **Path** al Backend.
2. **Backend** registra en **Postgres** -> Encola en **Celery**.
3. **Worker Celery** descarga de **MinIO** -> **Vectoriza** -> **Upsert** en Pinecone/PgVector.

Como ahora al llamar desde airflow va a ser "batch", es decir, mas de un archivo, hay que tener en cuenta el tema de crear en postgrest tanto para seguir el progreso los ingestas y estados separados y la global o batch en si.