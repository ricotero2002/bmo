# Resumen de Mejoras de Infraestructura y Conectividad

Este documento recopila cambios y configuraciones críticas realizadas durante la estabilización del stack de datos y BI que no estaban previamente documentados.

---

## 1. Optimización de Conexiones (PgBouncer)

### Problema
El plan Hobby/Free de Aiven PostgreSQL tiene un límite estricto de conexiones (slots). Metabase e Iceberg REST consumían estos slots rápidamente, causando errores de "Remaining connection slots are reserved for superusers".

### Solución
Se centralizaron las conexiones a través del **PgBouncer** interno de Airflow.
*   **Servicio**: `bmo-airflow-pgbouncer.personal-ai.svc.cluster.local`
*   **Puerto**: `6543`
*   **Base de Datos**: Se usa el alias `defaultdb` o `airflow` según la configuración del pool.

**Aplicación en Iceberg REST (`01-iceberg-rest.yaml`):**
```yaml
- name: CATALOG_URI
  value: "jdbc:postgresql://bmo-airflow-pgbouncer.personal-ai.svc.cluster.local:6543/defaultdb"
```

**Aplicación en Metabase:**
Se configuró la base de datos de Aiven en Metabase apuntando al host del PgBouncer interno en lugar de la URL directa de Aiven, desactivando SSL (PgBouncer maneja el SSL hacia Aiven).

---

## 2. Estabilización de Trino

### Ajustes de Memoria (Low-RAM Tuning)
Para que Trino corra estable en un entorno de ~2GB de RAM disponible en K3s:
*   **Coordinator**: Heap 512M, Límite 768Mi.
*   **Worker**: Heap 400M, Límite 768Mi.
*   **Configuración**: `query.max-memory-per-node` se redujo a 300MB para evitar OOMKills durante consultas complejas.

### Integración con Iceberg REST
Se corrigió el catálogo de Trino para usar el endpoint interno del servicio REST:
`iceberg.rest-catalog.uri=http://iceberg-rest-svc.personal-ai.svc.cluster.local:8181`

---

## 3. Mejoras en el Agente y RAG

### Lógica de Reintentos (Cold Start)
Se implementó la librería `tenacity` en `spark_utils.py` para manejar el tiempo de arranque de Spark Connect cuando escala desde cero.
*   **Intentos**: 15.
*   **Espera**: Hasta 3 minutos con backoff exponencial.

### Nuevas Capacidades de Ingesta (Fase 9)
Se habilitaron campos extendidos en la tabla `ingestion_status` (Oracle/Postgres):
*   `report`: Resumen generado por LLM Lite tras la ingesta.
*   `strategy`: Identificador de la técnica de segmentación (agentic vs markdown).
*   `processing_time`: Métrica de performance para dashboards de eficiencia.

---

## 4. Observabilidad (Metabase vs Grafana)

Se definió una estrategia clara de visualización:
*   **Metabase**: Preguntas de negocio, calidad del RAG (Faithfulness/Relevancy), costos de LLM y auditoría de chunks.
*   **Grafana**: Salud del clúster K8s, uso de CPU/RAM de los pods, estado de las colas de Celery y errores de infraestructura en tiempo real.
