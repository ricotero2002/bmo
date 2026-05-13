# Plan de Implementación: BI con Metabase y Reportes de Ingesta Asíncronos con Celery

Este documento detalla la planificación paso a paso para ejecutar la **Fase 1 (BI)** y la **Fase 2 (Event-Driven Analytics)** ajustando la arquitectura para usar **Celery** en lugar de Kafka, optimizando los recursos del clúster y la mantenibilidad.

---

## Fase 1: La Capa de Business Intelligence (BI) con Metabase

El objetivo es reemplazar Superset por Metabase para reducir el consumo de recursos (CPU/RAM) y acelerar la creación de dashboards conectados a nuestro Lakehouse (Iceberg).

### Paso 1: Limpieza de Recursos (Superset)
1. **Modificar `apps-deployment.yaml`**: Localizar y eliminar los bloques de `Deployment` y `Service` correspondientes a Superset.
2. **Ingress**: Si Superset estaba expuesto vía Traefik, eliminar su regla de enrutamiento (ej. `/superset`) de los manifiestos de Ingress correspondientes.
3. **Aplicar cambios**: Ejecutar `kubectl apply -f k8s/prod/apps-deployment.yaml` y verificar que el pod de Superset termina, liberando recursos valiosos.

### Paso 2: Despliegue de Metabase
1. **Agregar Metabase a `apps-deployment.yaml`**:
   - Crear un `Deployment` usando la imagen `metabase/metabase:latest`.
   - Definir `requests` y `limits` conservadores (Ej: Requests: 500m CPU / 1Gi RAM).
   - Variables de entorno básicas: `MB_DB_TYPE=postgres`, `MB_DB_DBNAME`, `MB_DB_PORT`, `MB_DB_USER`, `MB_DB_PASS`, `MB_DB_HOST` (apuntando a PgBouncer para su propia base de datos interna).
2. **Crear Service y Ruta**:
   - Añadir un `Service` en el puerto `3000`.
   - Modificar las reglas de Traefik para exponer Metabase (ej. `http://localhost:8081/metabase`).

### Paso 3: Conexión a la Capa Gold (Iceberg/Spark)
1. Dentro de Metabase, ir a Admin -> Databases.
2. Configurar una nueva conexión de tipo **Spark SQL**.
3. Apuntar al host `spark-thrift-svc.personal-ai.svc.cluster.local` en el puerto `10000` (el Thrift Server de Spark que expone el Lakehouse Iceberg).

### Paso 4: Construcción de Dashboards Core
- **Monitor de Costos**: Bar chart apilado conectando `fact_llm_costs` por día/usuario.
- **Calidad del Agente**: Line chart temporal de `avg(answer_relevancy)` y `avg(faithfulness)` de `fact_evaluations`.
- **Rendimiento**: Tabla de detalles cruzando latencias desde `fact_agent_performance`.

---

## Fase 2: Ciclo de Ingesta Automatizado (vía Celery)

Reemplazaremos la idea original de usar Kafka por **Celery**, aprovechando la infraestructura existente de workers y RabbitMQ/Redis, eliminando la necesidad de mantener un tópico de Kafka para este flujo.

### Paso 1: Modificación del Modelo de Datos (PostgreSQL)
Añadir al modelo SQLAlchemy principal (por ej. `Document` o `IngestionJob`) las nuevas métricas:
```python
summary_report = Column(Text, nullable=True)
ingestion_strategy = Column(String(50), nullable=True) # ej. "agentic" o "semantic"
total_chunks = Column(Integer, default=0)
processing_time_sec = Column(Float, default=0.0)
```
*(Se debe generar y aplicar la migración de Alembic correspondiente).*

### Paso 2: El Productor (Trigger en Celery)
En `src/workers/tasks.py`, modificaremos la tarea principal `process_document_task`. Al final del flujo exitoso (justo antes del `return`), encolaremos la nueva tarea asíncrona:

```python
# Al final de process_document_task()
duration = time.time() - start_time
sample_text = document.page_content[:500] if document.page_content else ""

# Lanzar la subtarea de reporte
generate_ingestion_report_task.apply_async(
    kwargs={
        "doc_id": doc_id,
        "filename": filename,
        "strategy": "agentic_chunking", # o parametrizado
        "chunks_generated": len(chunks),
        "processing_time_sec": duration,
        "sample_text": sample_text,
        "user_id": user_id
    },
    countdown=2 # Pequeño delay opcional
)
```

### Paso 3: El Consumidor / Generador (Nueva Tarea Celery)
En `src/workers/tasks.py` (o en un nuevo archivo lógico si se prefiere), crear la nueva tarea:

```python
@celery_app.task(
    bind=True,
    name="src.workers.tasks.generate_ingestion_report_task",
    max_retries=3,
    default_retry_delay=30,
)
def generate_ingestion_report_task(
    self, doc_id: str, filename: str, strategy: str, 
    chunks_generated: int, processing_time_sec: float, 
    sample_text: str, user_id: str
):
    # 1. Armar Prompt
    prompt = f"""Recibiste el documento '{filename}', procesado en {processing_time_sec:.2f} segundos 
    usando la estrategia '{strategy}', resultando en {chunks_generated} chunks. 
    Basado en este contexto: '{sample_text}', 
    redacta un reporte breve y amigable (máximo 3 líneas) de un asistente de IA notificando al usuario que su documento está listo."""

    # 2. Generar con LLM Lite (Ej. Llama 3 8B de NVIDIA NIM)
    llm = LLMFactory.create_lite() # Invocación al modelo rápido y gratuito
    response = llm.invoke(prompt)
    report_text = response.content

    # 3. Persistencia
    status_provider = StatusProvider()
    # Asumiendo una extensión a StatusProvider para guardar el reporte y las estadísticas
    status_provider.save_ingestion_report(
        doc_id=doc_id, 
        report=report_text, 
        chunks=chunks_generated, 
        strategy=strategy,
        time_sec=processing_time_sec
    )

    # 4. Notificación Push (Opcional)
    # emit_websocket_notification(user_id, report_text)
    # o send_telegram_alert(report_text)
    
    return {"status": "report_generated", "doc_id": doc_id}
```

### Paso 4: Registro y Configuración
Asegurarse de que `generate_ingestion_report_task` esté debidamente registrada y sea descubierta por `celery_app.py`. Los Celery Workers actuales (definidos en tu chart de Kubernetes y Airflow) podrán tomar esta tarea directamente de la cola, paralelizando la generación del resumen sin bloquear la ingesta de los próximos documentos.


Opción 1: Usar Trino (anteriormente PrestoSQL) - La Mejor Opción Técnica para Iceberg
Trino es el motor SQL por excelencia para leer formatos de tabla como Apache Iceberg en S3. Metabase tiene un conector nativo excelente para Trino.

Cómo funciona: Despliegas un clúster de Trino (1 Coordinator, opcionalmente N Workers) en tu Kubernetes. Lo configuras con un catálogo de Iceberg que apunta a tu iceberg-rest-svc y a OCI/S3. Metabase se conecta a Trino, y Trino lee el Lakehouse en tiempo real.

Pros: Es la arquitectura más "pura". No duplicas datos. Trino es ridículamente rápido para consultas BI y está diseñado específicamente para esto (a diferencia de Spark).

Contras: Consumo de recursos. Trino es una aplicación Java pesada. El coordinador por sí solo necesita al menos 2Gi a 4Gi de RAM para correr cómodo, y tiene que estar encendido 24/7 esperando que abras un dashboard en Metabase.

Opción 2: Spark Thrift Server (Directamente con Spark)
Mencionaste que usas Spark Connect. Spark Connect es un protocolo gRPC para aplicaciones cliente (como tu código Python), no sirve para herramientas BI. Para que Metabase se conecte a Spark, necesitas levantar el Spark Thrift Server (STS).

Cómo funciona: En lugar de (o además de) tu pod de Spark Connect, despliegas un pod de Spark corriendo el script start-thriftserver.sh. Este expone el puerto 10000. Metabase usa el driver de "Spark SQL" y se conecta a ese puerto.

Pros: Reutilizas Spark. No metes tecnologías nuevas (como Trino) al stack. Lees Iceberg directo.

Contras: Spark no es un buen motor interactivo para BI. El Thrift Server es esencialmente un driver de Spark que vive para siempre. Consume bastante RAM (mínimo 2Gi en idle), y las latencias de las consultas desde Metabase pueden tardar varios segundos (mientras que en Postgres tardarían milisegundos), arruinando la experiencia de usuario en el dashboard.

Opción 3: Hive
Veredicto: Descartado.

Por qué: Apache Hive como motor de ejecución está prácticamente obsoleto frente a Trino o Spark. Configurar HiveServer2 para leer Iceberg es un dolor de cabeza monumental, y es extremadamente lento. Hoy en día, Hive se usa casi exclusivamente por su Metastore (HMS), el cual tú ya reemplazaste inteligentemente por el Iceberg REST Catalog.

Conclusión y Recomendación (Por qué Postgres tiene sentido aquí)
El documento plan_metabase_celery_ingestion.md establece claramente un objetivo: "reducir el consumo de recursos (CPU/RAM)".

Si usas Trino o Spark Thrift, vas a tener un motor JVM gigante consumiendo 2-4GB de RAM las 24 horas del día, los 7 días de la semana, solo esperando a que de vez en cuando entres a ver un gráfico en Metabase.

Si usas Postgres, como Aiven ya te provee la base de datos administrada (y Metabase ya tiene su propia base interna ahí), el costo de almacenamiento de esas tablas Gold agregadas (que suelen ser pequeñas, de unos pocos miles de filas) es de kilobytes o megabytes. El consumo de cómputo en tu clúster de K8s en idle es CERO.

Mi recomendación:
Quédate con la estrategia de escribir las tablas Gold en PostgreSQL vía dbt.
Es la arquitectura conocida como "Headless BI" o "BI Extract". Usas la potencia bruta de Spark (que se levanta, procesa y se apaga) para hacer el trabajo pesado de transformar los datos en el Lakehouse, y empujas el resultado final agregado a una base transaccional rápida (Postgres) para que la herramienta visual (Metabase) vuele sin consumir recursos ociosos en tu clúster.

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