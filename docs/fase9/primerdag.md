# Fase 9 - Primer DAG (Spark + Airflow + dbt)

## Objetivo de este frente

Separar la orquestacion de datos del compose de Lakehouse actual:

1. Compose actual de Lakehouse: MinIO + REST catalog.
2. Compose nuevo de Data Tooling: Spark (Thrift) + Airflow.
3. dbt configurado para conectarse a Spark por Thrift y leer/escribir en catalogo Iceberg `lakehouse`.

## Revision de lo que ya habias agregado

### ingest_bronze.py

Aciertos detectados:

1. Tenias correctamente la configuracion de catalogo REST + S3FileIO.
2. El mapeo de columnas del CSV a snake_case estaba bien orientado.
3. El cast de `start_time` a timestamp era el paso correcto para Bronze usable.

Problemas detectados y corregidos:

1. Variable incorrecta al leer CSV: se usaba `csv_path` pero el nombre definido era `input_path`.
2. Script sin entrypoint ni argumentos: no era reutilizable desde Airflow.
3. Sin creacion explicita de namespace/tabla antes del append.
4. Sin metadatos de ingesta (`source_type`, `ingested_at`) para trazabilidad.

### sources.yml

Aciertos detectados:

1. Tenias la source en `lakehouse.bronze.raw_llm_traces` bien apuntada.
2. Ya habias agregado tests base en `run_id` (`unique`, `not_null`).

Mejoras aplicadas:

1. Tests de calidad por expresion (`latency_ms >= 0`, `total_tokens >= 0`) con severidad `warn`.
2. Tests adicionales de columnas clave (`start_time`, `status`, `total_tokens`, `total_cost_usd`).
3. Validacion de dominio para `status` con `accepted_values`.

## Cambios aplicados

### 1) Compose separado para Spark + Airflow

Archivo creado:

- `data_tooling/docker-compose.spark-airflow.yml`

Incluye:

1. Servicio `spark-thrift` (tabulario/spark-iceberg) con Thrift Server en puerto 10000.
2. Servicio `airflow` construido con Dockerfile propio y dependencias de data tooling.
3. Integracion hacia MinIO/REST del compose Lakehouse via `host.docker.internal` (puertos 9000 y 8181).
4. Guardrails de memoria para Spark:
   - `spark.executor.memory=2g`
   - `spark.memory.fraction=0.8`
   - `spark.sql.shuffle.partitions=200`

### 2) Imagen de Airflow para data tooling

Archivos creados:

- `data_tooling/airflow/Dockerfile`
- `data_tooling/airflow/requirements.txt`

Incluye paquetes necesarios para este frente:

1. `apache-airflow-providers-apache-spark`
2. `pyspark`
3. `dbt-core`
4. `dbt-spark[PyHive]`
5. `mlflow`

### 3) Ingesta Bronze funcional

Archivo actualizado:

- `data_tooling/airflow/tasks/ingest_bronze.py`

Ahora incluye:

1. Argumentos CLI (`--input-path`, `--source-type`, `--catalog`, `--target-table`, `--mode`).
2. SparkSession parametrizable por variables de entorno.
3. Normalizacion de columnas y cast de timestamp.
4. Creacion de namespace y tabla Iceberg si no existen.
5. Escritura en Bronze y conteo final de control.

### 4) DAG base ajustado al entorno

Archivo actualizado:

- `data_tooling/airflow/dags/pipeline_llm_telemetry.py`

Estado actual:

1. DAG diario de esqueleto con flujo `start -> ingest -> silver -> gold -> end`.
2. Ingesta usando `BashOperator` para ejecutar `ingest_bronze.py` (evita friccion de conexiones Spark en esta fase).
3. Tareas dbt con `dbt deps`, `dbt run` y `profiles-dir` apuntando al directorio montado.

### 5) Configuracion dbt contra Spark

Archivos actualizados/creados:

- `data_tooling/dbt/dbt_project.yml`
- `data_tooling/dbt/profiles.yml.example`
- `data_tooling/dbt/profiles.yml`
- `data_tooling/dbt/packages.yml`

Estado actual:

1. Perfil dbt configurado para `spark` + `thrift` (`spark-thrift:10000`).
2. Session properties para catalogo Iceberg REST y S3FileIO.
3. `packages.yml` agregado para `dbt_utils` (requerido por tests de expresion).

### 6) Source tests de Bronze

Archivo actualizado:

- `data_tooling/dbt/models/bronze/sources.yml`

Se agregaron tests de:

1. Unicidad y not null en `run_id`.
2. Not null en `start_time`, `status`, `total_tokens`, `total_cost_usd`.
3. Dominio de `status`.
4. Reglas de sanidad para latencia y tokens.

## Como levantar este setup

Precondicion:

1. Tener levantado el compose de Lakehouse (MinIO + REST).

Comandos:

1. `docker compose -f docker/docker-compose.yml up -d minio rest`
2. `docker compose -f data_tooling/docker-compose.spark-airflow.yml up -d --build`

Accesos:

1. Airflow UI: `http://localhost:8085`
2. Spark Thrift: `localhost:10000`

## Validaciones y checks

Checks intentados durante esta iteracion:

1. Validacion de sintaxis Python (ingest y DAG).
2. Validacion de `docker compose config` para el compose nuevo.

Resultado:

1. Los checks no se ejecutaron porque fueron omitidos manualmente en esta corrida del asistente.
2. Quedan como paso recomendado inmediato antes de primer run del DAG.

Comandos recomendados para validar ahora:

1. `python -m py_compile data_tooling/airflow/tasks/ingest_bronze.py`
2. `python -m py_compile data_tooling/airflow/dags/pipeline_llm_telemetry.py`
3. `docker compose -f data_tooling/docker-compose.spark-airflow.yml config`

## Pendientes siguientes (cuando quieras)

1. Definir SQL real de `silver/stg_agent_runs.sql`.
2. Definir SQL reales de modelos Gold.
3. Reemplazar input CSV por lectura desde MinIO o extractor MLflow.
4. Endurecer credenciales via variables de entorno/secret manager.
