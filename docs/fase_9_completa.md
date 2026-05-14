# Fase 9 - Implementación Integral de Plataforma: Lakehouse, ELT y AI Engineering

Este documento consolida toda la fase 9 de BMO, detallando la evolución de una arquitectura RAG operativa hacia una plataforma de datos y AI Engineering de nivel producción. Se incluyen implementaciones, desafíos, descartes y soluciones técnicas aplicadas.

## 1. Resumen Ejecutivo
La Fase 9 se centró en la robustez, escalabilidad y observabilidad del sistema. Se logró estabilizar la infraestructura de Kafka, implementar un Lakehouse moderno (Iceberg + Spark), automatizar la ingesta masiva (Notion/Obsidian) y establecer un pipeline de evaluación de calidad (LLM-as-a-Judge) con monitoreo en tiempo real.

---

## 2. Infraestructura y Plataforma (Core)

### 2.1 Estabilización de Kafka SSL (Frente 0)
*   **Problema**: Errores recurrentes de `legacy provider` y SASL handshake en OKE (Oracle Kubernetes Engine) debido a incompatibilidades de OpenSSL.
*   **Solución**: Se corrigió el runtime de OpenSSL en los contenedores y se actualizaron los manifests de K8s para inyectar correctamente los certificados y configuraciones de Aiven.
*   **Resultado**: Cero errores de conexión SSL en producción.

### 2.2 El Lakehouse (Iceberg + Spark + MinIO)
Se implementó una arquitectura de Lakehouse desacoplada del clúster de aplicaciones principal:
*   **Storage**: Oracle Object Storage como object storage compatible con S3, organizado en zonas (bronze, silver, gold, warehouse).
*   **Table Format**: **Apache Iceberg**, proporcionando transacciones ACID, Time Travel y evolución de esquemas.
*   **Compute**: **Apache Spark** migrado a arquitectura **Spark Connect (gRPC)**. Esto permitió tener workers de Airflow "ligeros" (thin clients) que delegan el procesamiento pesado a un servidor centralizado.
*   **Catalog**: Iceberg REST Catalog para la gestión centralizada de metadatos.

### 2.3 Optimización de Conexiones (PgBouncer)
*   **Problema**: Saturación de slots en Aiven PostgreSQL (Plan Hobby) por conexiones simultáneas de Metabase, Airflow e Iceberg REST.
*   **Solución**: Implementación de **PgBouncer** como pool de conexiones centralizado, reduciendo drásticamente la carga sobre la base de datos operativa.

---

## 3. Data Engineering y Pipelines (ELT)

### 3.1 Arquitectura Medallón
Se estandarizó el procesamiento en tres capas lógicas:
1.  **Bronze (Raw)**: Datos crudos (JSON/CSV/Kafka) sin alteraciones.
2.  **Silver (Staging)**: Limpieza, tipado, normalización de fechas y aplanamiento de JSON mediante **dbt**.
3.  **Gold (Business)**: Modelos estrella (Hechos y Dimensiones) optimizados para BI y para que el agente los consulte vía Text-to-SQL.

### 3.2 Pipeline de Telemetría (LangSmith → Lakehouse)
Flujo automatizado para auditar el desempeño del agente:
*   **Extracción**: Uso de `boto3` para descargar trazas de LangSmith hacia una Landing Zone en OCI/MinIO.
*   **Carga**: Registro en tablas Iceberg Bronze.
*   **Evaluación**: Integración de **DeepEval** con modelos de **NVIDIA NIM** para calificar Faithfulness (Fidelidad) y Answer Relevancy (Relevancia).
*   **Agregación**: dbt consolida métricas de costos, latencia y calidad en la capa Gold.

### 3.3 Ingesta Masiva (Pattern Claim-Check)
*   **Sincronización de Notion/Obsidian**: Implementado con **Airflow Dynamic Task Mapping (`.expand()`)**, permitiendo escalar horizontalmente y procesar múltiples usuarios en paralelo.
*   **Claim-Check**: La API recibe referencias de archivos en Storage (Oracle) en lugar de los bytes en RAM, evitando cuellos de botella.
---

## 4. AI Engineering y LLMOps

### 4.1 Estandarización del Juez (LLM-as-a-Judge)
*   **Modelos**: Se estandarizaron jueces de alta confiabilidad en NVIDIA NIM (`abacusai/dracarys-llama-3.1-70b` y `mistralai/mistral-large-3`).
*   **Limpieza de "Thinking" Blocks**: Implementación de filtros Regex para eliminar razonamientos internos (`<think>...</think>`) que rompen el parseo de JSON en modelos como Qwen o Maverick.
*   **Reportes Automáticos**: Generación de resúmenes de 2-3 líneas post-ingesta persistidos en el `summary_report` de la base de datos para feedback inmediato al usuario.

---

## 5. Visualización y BI (Observabilidad)

### 5.1 Metabase vs Grafana
Se definió un rol claro para cada herramienta:
*   **Metabase (BI & Quality)**: Dashboards de calidad RAG, costos de tokens por usuario, auditoría de alucinaciones (razones de falla de fidelidad) y registro de errores en runs.
*   **Grafana (Infrastructure)**: Monitoreo de salud del clúster K8s, uso de CPU/RAM, reinicios de pods y estado de las colas de Celery/Redis.

### 5.2 Trino (Motor de Consultas)
Se integró **Trino** para permitir consultas SQL federadas sobre el Lakehouse Iceberg con baja latencia, optimizado para correr en entornos de recursos limitados (tuning de memoria a 2GB).

---

## 6. Desafíos, Errores y Soluciones

| Error / Desafío | Contexto | Solución Aplicada |
| :--- | :--- | :--- |
| **403 Forbidden OCI** | Hadoop S3A (SDK v1) no firmaba correctamente los payloads exigidos por OCI. | Descarga previa con `boto3` al `/tmp` local del worker antes de pasar a Spark. |
| **OOM / SIGKILL 137** | Spark local saturaba la memoria del pod en K8s. | Migración a **Spark Connect** y limitación de hilos con `local[2]`. |
| **Conflicto OTEL** | MLflow secuestraba el TracerProvider de Grafana. | **Descarte de MLflow**; transición a LangSmith con rastreo selectivo. |
| **Async Context Loss** | El autologging de MLflow perdía ContextVars en flujos asíncronos. | Se eliminó MLflow y se usó el context manager nativo de LangChain para tracing. |
| **Thrift default namespace** | Spark Thrift rechazaba conexiones si no existía el namespace `default`. | Creación manual vía API REST y posterior automatización en el bootstrap. |

---

## 7. Skills, Herramientas y Frameworks

### Skills Técnicas
*   **Big Data**: Modelado de Lakehouse, optimización de archivos Parquet, particionamiento en Iceberg.
*   **Data Engineering**: Pipelines ELT/ETL, CDC (Change Data Capture), Orquestación distribuida, Dynamic Task Mapping.
*   **AI Engineering / LLMOps**: Evaluación de modelos (LLM-as-a-Judge), Prompt Engineering para reportes, Manejo de inferencia estructurada (JSON), Tracing de grafos.
*   **Infraestructura**: K8s (OKE/K3s), Autoscaling con KEDA, Gestión de secretos, Proxy de base de datos (PgBouncer).
*   **BI & Data Modeling**: Diseño de Esquema Estrella (Hechos/Dimensiones), Visualización de datos de negocio.
*   **Automatizacion**: De ingesta de notion y de las metricas en forma medallon + LLMOps.

### Stack Tecnológico
*   **Orquestación**: Apache Airflow 2.10.5 (CeleryExecutor).
*   **Procesamiento**: Apache Spark 3.5.x (Connect & Thrift), dbt-spark.
*   **Almacenamiento**: Apache Iceberg, MinIO, OCI Object Storage.
*   **Motores de Consulta**: Trino, Spark SQL.
*   **Mensajería y Eventos**: Apache Kafka, Redis, RabbitMQ.
*   **Bases de Datos**: Aiven PostgreSQL, Oracle Autonomous Database.
*   **Visualización**: Metabase, Grafana.
*   **IA/LLM**: LangChain, LangGraph, DeepEval, NVIDIA NIM, OpenRouter.
*   **Observabilidad**: LangSmith, Prometheus, OpenTelemetry.

---
*Este documento marca el cierre técnico de la Fase 9 y sirve como base para la escalabilidad futura de BMO.*
