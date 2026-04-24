# Refactorización de Arquitectura de Telemetría (Fase 9)

Se ha realizado una refactorización profunda del pipeline de datos para asegurar escalabilidad, desacoplamiento de infraestructura y mantenibilidad.

## 1. Abstracción de Almacenamiento (Object Storage)
Se introdujo el `DataLakeProvider` para centralizar las operaciones de escritura en el Data Lake.
- **Ubicación:** [data_lake_provider.py](file:///d:/BMO/bmo/src/providers/storage/data_lake_provider.py)
- **Beneficio:** Cambiar de MinIO a Oracle Object Storage o AWS S3 es transparente; solo requiere actualizar las variables de entorno sin tocar el código de los procesos de extracción.

## 2. Extracción Robusta (Streaming & Chunks)
El proceso de extracción desde LangSmith fue rediseñado para manejar grandes volúmenes de datos.
- **Chunking:** Se procesan lotes de 1000 registros (`CHUNK_SIZE`). Esto evita errores de memoria (OOM) en los workers de Airflow.
- **Logging Detallado:** Se añadieron logs de depuración que muestran columnas, ejemplos de datos y conteos totales.
- **Ubicación:** [extract_langsmith.py](file:///d:/BMO/bmo/data_tooling/airflow/tasks/extract_langsmith.py)

## 3. Utilidades de Spark e Iceberg (DRY)
Se eliminó la duplicación de código de configuración de Spark.
- **Centralización:** `spark_utils.py` contiene la lógica para crear sesiones de Spark con Iceberg REST, manejar namespaces y expirar snapshots.
- **Ubicación:** [spark_utils.py](file:///d:/BMO/bmo/src/providers/lakehouse/spark_utils.py)

## 4. Orquestación Moderna (DBT sobre Spark)
Se optimizó el flujo de transformación eliminando scripts intermedios de PySpark.
- **Silver Layer:** Ahora se gestiona puramente con **dbt**. dbt se conecta al Spark Thrift Server y ejecuta el SQL necesario para crear y actualizar las tablas Iceberg.
- **Registro en Bronze:** Un script ligero (`register_bronze.py`) se encarga de mover los datos de la Landing Zone (Parquet) a la tabla formal de Iceberg.
- **Ubicación del DAG:** [pipeline_llm_telemetry.py](file:///d:/BMO/bmo/data_tooling/airflow/dags/pipeline_llm_telemetry.py)

## 5. Limpieza de Código
Se eliminaron los siguientes archivos obsoletos:
- `data_tooling/airflow/tasks/ingest_bronze.py` (Reemplazado por `register_bronze.py` y `spark_utils.py`)
- `data_tooling/airflow/tasks/spark_silver.py` (Reemplazado por dbt nativo)

## 6. Próximos Pasos
- Validar la conexión del `dbt-spark` adapter con el puerto 10000 del contenedor `spark-thrift`.
- Configurar el `profiles.yml` de dbt para usar el método `thrift`.
