# Fase 9 - Implementacion Integral de Plataforma (Kafka, Lakehouse, ELT, LLMOps)

## Resumen Ejecutivo

Esta fase consolida la evolucion de BMO desde una arquitectura RAG operativa hacia una plataforma de datos y AI Engineering de nivel produccion, con foco en:

1. Estabilidad critica de Kafka SSL en OKE.
2. Capa de datos escalable tipo Lakehouse.
3. Ingesta masiva batch + streaming.
4. Analitica ELT con modelos de negocio para agentes y dashboards.
5. LLMOps con trazabilidad, evaluacion automatica y alertas.
6. Gobernanza de embeddings y migraciones sin downtime.

## Alcance

Incluido:

- Fix Kafka SSL legacy provider.
- Base Lakehouse local/cloud-ready (MinIO + Iceberg + Spark).
- Pipelines de ingesta y transformacion.
- Integracion OpenRouter en LLMFactory.
- Metrica de negocio en Grafana y opcion BI.
- Reporte automatico de ingesta al finalizar procesamiento.

Excluido:

- Features no relacionadas a plataforma de datos/LLMOps fuera del backlog compartido.

## Arquitectura Objetivo

### 1) Capa Operacional

- FastAPI + LangGraph + Celery + Kafka + PostgreSQL + Vector Store.
- Mantiene low-latency para operaciones transaccionales.

### 2) Capa de Datos (Lakehouse)

- Storage: MinIO (zonas raw/silver/gold).
- Table format: Apache Iceberg.
- Compute: Spark (y DuckDB para consultas locales puntuales).

### 3) Capa Analitica

- ELT con dbt para modelos staging/fact/dim.
- Exposicion de tablas para Text-to-SQL del agente y dashboards.

### 4) Capa LLMOps

- MLflow para trazas y experiment tracking.
- Evaluacion automatica diaria (DeepEval + muestreo).
- Alertas por degradacion de calidad.

## Plan por Frentes

### Frente 0 - Kafka SSL (bloqueante)

- Corregir runtime OpenSSL en contenedores y manifests OKE.
- Validar producer/consumer con Aiven.
- Cerrar con rollout canary y rollback probado.

### Frente A - Lakehouse

- Crear catalogo Iceberg y primeras tablas para logs e ingesta.
- Definir particiones, retencion y naming standards.

### Frente B - Ingesta batch + streaming

- DAG Airflow para extraccion incremental y carga a raw.
- Emision de eventos `ingestion_events` y procesado paralelo con KEDA.

### Frente C - ELT

- Construir capa Bronze/Silver/Gold con dbt.
- Modelos iniciales: `stg_logs`, `fact_agent_interactions`, `dim_tools`, `fact_ingestion_jobs`.

### Frente D - LLMOps

- Tracking MLflow con backend en Postgres y artifacts en MinIO.
- DAG nocturno LLM-as-a-Judge con thresholds y alertas.

### Frente E - Reporte de ingesta

- Agregar `summary_report` en `ingestion_jobs`.
- Publicar `ingestion_completed` y consumir para generar resumen con modelo Lite.

### Frente F - LLMFactory OpenRouter

- Integrar `langchain-openrouter` con listas HEAVY/LITE y especialistas.
- Mantener fallback nativo y captura de uso de tokens.

### Frente G - Metricas y BI

- Grafana conectado a Postgres analytics con usuario read-only.
- Metabase para analitica self-service y consumo de negocio.

### Frente H - Migracion de embeddings

- Nueva coleccion/indice por version de embedding.
- Re-embedding por lotes desde MinIO + metadatos existentes.
- Cutover controlado y rollback.

## Entregables

1. Pipeline Kafka estable en OKE sin errores SSL legacy.
2. Capa Lakehouse operativa con al menos una tabla Iceberg productiva.
3. Pipeline ELT publicando hechos/dimensiones de negocio.
4. MLflow operativo con evaluacion automatica y alertas.
5. Reporte automatico de ingesta persistido y exponible al frontend.
6. LLMFactory actualizado a OpenRouter con estrategia de modelos.
7. Dashboards de negocio y runbooks operativos.

## Criterios de Exito

1. Cero errores `legacy provider` / SASL handshake en produccion.
2. Ingesta masiva estable bajo incremento de eventos (KEDA escalando correctamente).
3. Analitica consultable sin cargar la base operacional.
4. Trazas de ejecucion y metricas LLM disponibles historicamente.
5. Degradaciones detectadas automaticamente con alertas.
6. Migracion de embeddings completada sin perdida de recuperacion relevante.

## Riesgos y mitigaciones

1. Complejidad de stack: implementar por fases y con flags.
2. Costos de evaluacion: muestreo estratificado diario.
3. Drift entre entornos: templates y variables estandarizadas por entorno.
4. Duplicidad de datos: convenciones de particion y llaves idempotentes.

## Secuencia Recomendada

1. Kafka SSL fix (go/no-go).
2. LLMFactory OpenRouter base.
3. Lakehouse bootstrap.
    3.1 probar el lakehouse. (Para esto se genero un grafo simple usando un csv). 
4. Mlflow (solo iniciarlo y generar alguna metrica, no parte de evaluaciones). (No se uso finalmente)
5. ELT dbt. (Usando langsmith)
6. Evaluaciones en dag.
7. Ingesta batch/streaming.
    7.1. Falta hacer seguro los endpoints que se llaman desde airflow para solo ser usados por eso.
    7.2. Ver como pasar todo a el kluster de kubernetes.
    7.3. Ver exactamente como funciona el tema de que te indique solo lo actualizado en notion, que pasa si borras cosas?


8. Reporte de ingesta.
9. Dashboards y BI.

## Notas Operativas

- Todo cambio de infraestructura va con smoke tests y rollback.
- Evitar `latest` en imagenes productivas; usar tags inmutables.
- Mantener secretos centralizados y permisos minimos (least privilege).

docker compose -f data_tooling/docker-compose.spark-airflow.yml up -d --build


Pendientes:
pasar a usar el spark de conection y no local en worker
sacar (si se puede) los jas del dockerfile
la parte de metabase
la parte de el analisis de la ingesta



10.42.0.154
 ▼ Log message source details
*** Found logs served from host http://10.42.0.154:8793/log/dag_id=pipeline_llm_telemetry/run_id=manual__2026-05-08T18:34:53+00:00/task_id=spark_evaluate_gold/attempt=5.log
 ▲▲▲ Log group end
[2026-05-11, 16:59:17 UTC] {local_task_job_runner.py:123} ▶ Pre task execution logs
[2026-05-11, 16:59:30 UTC] {subprocess.py:78} INFO - Tmp dir root location: /tmp
[2026-05-11, 16:59:30 UTC] {subprocess.py:88} INFO - Running command: ['/usr/bin/bash', '-c', 'python3 /opt/airflow/tasks/spark_evaluator.py --ds 2026-05-08 --sample-fraction 1 --max-runs 50']
[2026-05-11, 16:59:30 UTC] {subprocess.py:99} INFO - Output:
[2026-05-11, 16:59:37 UTC] {subprocess.py:106} INFO - Traceback (most recent call last):
[2026-05-11, 16:59:37 UTC] {subprocess.py:106} INFO -   File "/opt/airflow/tasks/spark_evaluator.py", line 18, in <module>
[2026-05-11, 16:59:37 UTC] {subprocess.py:106} INFO -     from src.evals.eval_utils import NvidiaJudge
[2026-05-11, 16:59:37 UTC] {subprocess.py:106} INFO -   File "/opt/project/src/evals/eval_utils.py", line 8, in <module>
[2026-05-11, 16:59:37 UTC] {subprocess.py:106} INFO -     from src.providers.record_manager.factory import RecordManagerFactory
[2026-05-11, 16:59:37 UTC] {subprocess.py:106} INFO -   File "/opt/project/src/providers/record_manager/factory.py", line 6, in <module>
[2026-05-11, 16:59:37 UTC] {subprocess.py:106} INFO -     from langchain_classic.indexes import SQLRecordManager
[2026-05-11, 16:59:37 UTC] {subprocess.py:106} INFO - ModuleNotFoundError: No module named 'langchain_classic'
[2026-05-11, 16:59:37 UTC] {subprocess.py:110} INFO - Command exited with return code 1
[2026-05-11, 16:59:38 UTC] {taskinstance.py:3313} ERROR - Task failed with exception
Traceback (most recent call last):
  File "/home/airflow/.local/lib/python3.11/site-packages/airflow/models/taskinstance.py", line 763, in _execute_task
    result = _execute_callable(context=context, **execute_callable_kwargs)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/airflow/.local/lib/python3.11/site-packages/airflow/models/taskinstance.py", line 734, in _execute_callable
    return ExecutionCallableRunner(
           ^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/airflow/.local/lib/python3.11/site-packages/airflow/utils/operator_helpers.py", line 252, in run
    return self.func(*args, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/airflow/.local/lib/python3.11/site-packages/airflow/models/baseoperator.py", line 424, in wrapper
    return func(self, *args, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/airflow/.local/lib/python3.11/site-packages/airflow/operators/bash.py", line 276, in execute
    raise AirflowException(
airflow.exceptions.AirflowException: Bash command failed. The command returned a non-zero exit code 1.
[2026-05-11, 16:59:38 UTC] {taskinstance.py:1226} INFO - Marking task as UP_FOR_RETRY. dag_id=pipeline_llm_telemetry, task_id=spark_evaluate_gold, run_id=manual__2026-05-08T18:34:53+00:00, execution_date=20260508T183453, start_date=20260511T165918, end_date=20260511T165938
[2026-05-11, 16:59:41 UTC] {taskinstance.py:341} ▶ Post task execution logs