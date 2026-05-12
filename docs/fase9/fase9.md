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



Me falta:
Dashboards y BI.


2. Metabase + datos del lakehouse
El metabase-deployment.yaml que ya tenés está bien configurado. El problema es el conector: el plan menciona Spark Thrift en puerto 10000, pero migraste a Spark Connect (gRPC), que Metabase no soporta directamente.
La solución más simple: materializar gold en PostgreSQL con dbt
Ya tenés Aiven PostgreSQL. En lugar de conectar Metabase a Spark, usás dbt para escribir las tablas gold como vistas/tablas en Postgres, y Metabase las lee directamente. Metabase tiene soporte nativo excelente para PostgreSQL.
Agregás un profiles.yml para un target analytics adicional:
yaml# En dbt/profiles.yml, agregar output adicional
bmo_lakehouse:
  target: prod
  outputs:
    prod:
      type: spark
      method: session
      host: NA
      schema: silver
      threads: 2

    analytics:          # ← target para Metabase
      type: postgres
      host: pg-3ad5269f-bmo.d.aivencloud.com
      port: 23645
      user: "{{ env_var('AIVEN_PG_USER') }}"
      password: "{{ env_var('AIVEN_PG_PASSWORD') }}"
      dbname: defaultdb
      schema: analytics
      threads: 2
      sslmode: require
Y en el DAG, agregas un task al final:
python# pipeline_llm_telemetry.py
dbt_analytics_task = BashOperator(
    task_id="dbt_run_analytics",
    execution_timeout=timedelta(minutes=10),
    cwd="/opt/airflow/dbt",
    bash_command=(
        DBT_BASE.replace("--profiles-dir /opt/airflow/dbt", 
                         "--profiles-dir /opt/airflow/dbt --target analytics")
        + "--select models/analytics"
    ),
)

# ... >> dbt_gold_task >> dbt_analytics_task >> end
Los modelos de analytics en dbt son simplemente lecturas de las gold de Iceberg que Spark ya calculó:
sql-- dbt/models/analytics/mart_agent_quality.sql
-- {{ config(materialized='table') }}

SELECT
    date,
    COUNT(*) AS total_runs,
    ROUND(AVG(answer_relevancy), 3) AS avg_relevancy,
    ROUND(AVG(faithfulness), 3) AS avg_faithfulness,
    COUNT(CASE WHEN answer_relevancy >= 0.7 THEN 1 END) AS passing_runs
FROM {{ source('gold', 'agent_evaluations') }}
GROUP BY date
ORDER BY date DESC
sql-- dbt/models/analytics/mart_agent_errors.sql  
-- {{ config(materialized='table') }}

SELECT
    date,
    COUNT(*) AS error_count,
    error_message,
    COUNT(*) OVER (PARTITION BY date) AS total_errors_that_day
FROM {{ source('gold', 'agent_errors') }}
GROUP BY date, error_message
ORDER BY date DESC, error_count DESC
Metabase se conecta a Postgres → schema analytics → dashboards directos, sin necesitar Spark ni Iceberg en tiempo de query.


Actualizar alembic
Actualizar todas las imagenes de docker
probar el webserver