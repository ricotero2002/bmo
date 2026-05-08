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
