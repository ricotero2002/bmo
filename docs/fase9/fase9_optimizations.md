# Reporte de Optimizaciones y Mejoras (Fase 9)

Este documento detalla las optimizaciones y correcciones realizadas para mejorar la eficiencia del pipeline, la robustez de las evaluaciones de IA y el rendimiento de la infraestructura de Airflow.

## 1. Eficiencia en Spark Connect (`spark_evaluator.py`)

### El Problema
Se detectó que el script de evaluación ejecutaba múltiples llamadas a `.count()` sobre los mismos DataFrames. En la arquitectura **Spark Connect**, cada llamada a `.count()` implica un round-trip gRPC completo al servidor, lo que introducía latencia innecesaria y disparaba jobs de Spark redundantes.

### La Solución
Se refactorizó `spark_evaluator.py` para:
- Almacenar el conteo en variables locales (`error_count`, `success_count`).
- Reutilizar estas variables para el logging y la toma de decisiones lógicas.
- Reducir el número de jobs de Spark ejecutados por cada tarea de evaluación.

---

## 2. Robustez del Servidor Spark (`02-spark-connect.yaml`)

### Mejoras de Memoria
El servidor de Spark Connect estaba utilizando el valor por defecto para el heap de la JVM (1Gi), a pesar de tener límites de recursos de 5Gi en Kubernetes. Esto causaba una subutilización de la memoria disponible y posibles cuellos de botella en la gestión de metadatos de Iceberg.

**Cambios Aplicados:**
- Se configuró explícitamente `spark.driver.memory=3g`.
- Se configuró `spark.driver.memoryOverhead=512m`.
- Esto asegura que el servidor tenga suficiente margen para manejar las sesiones gRPC y el acceso al catálogo REST de Iceberg de forma eficiente.

---

## 3. Optimización del Juez de IA (`llm.py` y `eval_utils.py`)

### Corrección de Prefijos NIM
Se detectó un error en el mapeo de prefijos para los modelos de **Abacus AI**. El nombre del modelo en NIM (`abacusai/...`) no coincidía con el prefijo configurado (`abacus.ai/`), lo que causaba que las peticiones cayeran al fallback de OpenRouter, fallando con errores 400. Se añadió el prefijo correcto `abacusai/`.

### Manejo de Modelos "Thinking" (Qwen3/Maverick)
Los modelos más avanzados (como Qwen3) a veces generan texto de razonamiento (ej: `<think>...</think>`) antes de entregar el JSON. Esto rompía el parseo de `deepeval`.

**Mejoras:**
- **Limpieza de JSON**: Se actualizó `_clean_json` en `eval_utils.py` con una expresión regular para eliminar bloques de pensamiento de forma robusta.
- **Modelos de Evaluación**: Se seleccionaron jueces específicos altamente confiables para JSON:
    - **Primario**: `abacusai/dracarys-llama-3.1-70b-instruct` (fine-tuneado para tareas estructuradas).
    - **Secundario**: `mistralai/mistral-large-3-675b-instruct-2512` (excelente seguimiento de instrucciones JSON).
    - **Fallback**: `meta/llama-4-maverick-17b-128e-instruct`.
- **Exclusión de Modelos "Thinking"**: Se configuró `create_judge` para ignorar `HEAVY_MODEL_NAMES`, evitando que modelos como Qwen3 introduzcan "babbling" o razonamientos que rompan el parseo de DeepEval.

---

## 4. Nuevo Reporte de Ingesta (Fase 2)

Se implementó una nueva funcionalidad para notificar al usuario sobre el resultado del procesamiento de sus documentos.

### Componentes:
- **Modelo SQL**: Se añadieron columnas a `IngestionJob` para persistir el `report` generado por IA, el conteo de `chunks`, la `strategy` utilizada y el `processing_time`.
- **Tarea Celery**: Se creó `generate_ingestion_report_task` que utiliza un modelo LLM ligero para redactar un resumen de 2-3 líneas sobre el documento procesado.
- **StatusProvider**: Se añadió el método `save_ingestion_report` para centralizar la persistencia de estas métricas.

---

## 5. Rendimiento del Webserver de Airflow

Para mitigar la lentitud de la interfaz de usuario en el clúster K3d, se aplicaron ajustes de "tuning" de producción.

### Cambios en `helm-values.yaml`:
- **Escalado de Gunicorn**: Se aumentó de 1 a 2 workers de Gunicorn. Esto permite manejar requests concurrentes sin bloquear la UI.
- **Backend de Sesión**: Se cambió de `securecookie` a `database`. Al usar PgBouncer, esto acelera el manejo de sesiones y permisos.
- **Optimización de UI**:
    - Se limitó el tamaño de página a 25 DAGs.
    - Se deshabilitó el reload automático en cambios de plugins.
    - Se redujo el timeout del worker a 60s para una respuesta más ágil.
- **Recursos**: Se aumentó el límite de memoria del webserver a 2Gi para dar cabida al segundo worker y al cache de la base de datos.
