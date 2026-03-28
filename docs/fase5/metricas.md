¡Llegaste al Santo Grial de la observabilidad! Ver todas estas métricas de golpe puede ser abrumador, pero en realidad es la mina de oro que usan los ingenieros SRE (Site Reliability Engineers) para saber exactamente qué está pasando en el clúster sin tener que mirar ni un solo log.

Las métricas que estás viendo se dividen en **4 grandes categorías**. Aquí tienes la enciclopedia exacta de qué son, para qué sirven y (lo más importante) cómo combinarlas en Grafana para crear un dashboard espectacular.

---

### 1. Métricas de Negocio (Tus métricas personalizadas `bmo_*`)
Estas son las más valiosas porque las creaste tú. Miden el éxito de tu aplicación desde el punto de vista del usuario.

| Métrica | Tipo | ¿Para qué sirve? |
| :--- | :--- | :--- |
| `bmo_documents_processed_total` | Counter | Cuántos documentos ha procesado tu sistema. Ideal para saber el volumen de uso de tu IA. |
| `bmo_extraction_duration_seconds_bucket` | Histogram | Cuánto tiempo tarda tu código en extraer el texto (ej. MarkItDown). Te permite calcular el percentil 95 (P95) de lentitud. |
| `bmo_extraction_duration_seconds_count` | Counter | Cuántas extracciones se hicieron (parte matemática del histograma). |
| `bmo_extraction_duration_seconds_sum` | Counter | Suma total del tiempo gastado extrayendo texto. |

---

### 2. Métricas de Celery (El motor de trabajo)
Generadas por tu `celery-exporter`. Miden la salud de tu procesamiento en background (RabbitMQ + Workers).

| Métrica | Tipo | ¿Para qué sirve? |
| :--- | :--- | :--- |
| `celery_task_sent_total` | Counter | Cuántas tareas envió tu API a la cola. |
| `celery_task_received/started_total` | Counter | Cuántas tareas agarró el worker y empezó a ejecutar. |
| `celery_task_succeeded_total` | Counter | **Crucial:** Tareas completadas con éxito. |
| `celery_task_failed_total` | Counter | **Crucial:** Tareas que explotaron por un error de código o timeout. |
| `celery_task_runtime_bucket` | Histogram | Cuánto tardó el worker en procesar un documento de inicio a fin (incluyendo Pinecone, OCI, etc). |
| `celery_queue_length` | Gauge | **El termómetro del clúster:** Cuántos mensajes están atascados en RabbitMQ esperando ser procesados. |
| `celery_active_worker_count` | Gauge | Cuántos pods/workers de Celery tienes vivos y listos para trabajar. |

---

### 3. Métricas de Infraestructura (`process_*` y `go_*`)
Estas métricas miden los recursos físicos (CPU, RAM). 
*(Nota: Las métricas `go_*` provienen de los contenedores que están escritos en Go, como el Celery Exporter, el OTEL Collector o Traefik. No miden tu código Python, miden la salud de tus "vigilantes").*

| Métrica | Tipo | ¿Para qué sirve? |
| :--- | :--- | :--- |
| `process_cpu_seconds_total` | Counter | Cuánta CPU total está consumiendo un contenedor. |
| `process_resident_memory_bytes` | Gauge | **Alerta roja:** Cuánta memoria RAM real (RSS) está usando el contenedor. Si esto toca tu límite de K8s, el pod morirá por OOM (Out Of Memory). |
| `process_open_fds` | Gauge | Descriptores de archivos abiertos (conexiones de red, archivos leídos). Si sube infinitamente, tienes un *memory leak* de conexiones. |
| `go_goroutines` | Gauge | (Interna de Go). Cuántos hilos de ejecución ligeros tiene el exporter. |
| `go_memstats_alloc_bytes` | Gauge | (Interna de Go). RAM consumida por las herramientas de monitoreo. |

---

### 4. Métricas de Red (`traefik_*` y `scrape_*`)
Miden el tráfico HTTP que entra a tu clúster antes de tocar tu API.

| Métrica | Tipo | ¿Para qué sirve? |
| :--- | :--- | :--- |
| `traefik_entrypoint_requests_total` | Counter | Cuántas peticiones HTTP (GET, POST) llegaron a tu clúster. |
| `traefik_entrypoint_request_duration_seconds` | Histogram | Latencia de red. Cuánto tardó el usuario en recibir la respuesta desde que hizo el clic. |
| `scrape_duration_seconds` | Gauge | Cuánto tarda el OTEL Collector en ir a preguntarle los datos al Celery Exporter. (Si es muy alto, el clúster está saturado). |

---

### 🧠 ¿Cómo combinar todo esto en Grafana? (Los "Golden Dashboards")

Para que un dashboard sea útil, no debes poner gráficos al azar. Debes responder preguntas de negocio y operaciones combinando las métricas usando **PromQL** (el lenguaje de consultas de Prometheus/Grafana). Aquí tienes 3 ejemplos de paneles que deberías armar:

#### Panel 1: "La Tubería de Ingestión" (Salud General)
Combina el trabajo pendiente con tu fuerza laboral. Si la cola sube y los workers están estáticos, tienes un problema (o KEDA está actuando).
* **Línea A (Atasco):** `celery_queue_length{queue_name="ingest_q"}`
* **Línea B (Capacidad):** `celery_active_worker_count`
* *Diagnóstico:* Cuando la línea A sube, deberías ver a la línea B subir poco después gracias a KEDA.

#### Panel 2: "Tasa de Éxito de la IA" (Calidad)
Combina las métricas de éxito y error para ver tu porcentaje de fallos.
* **Fórmula (Éxito %):** `sum(rate(celery_task_succeeded_total[5m])) / (sum(rate(celery_task_succeeded_total[5m])) + sum(rate(celery_task_failed_total[5m]))) * 100`
* *Diagnóstico:* Esto te dará un hermoso gráfico de porcentaje. Debería estar siempre al 100%. Si cae al 80%, sabes que 1 de cada 5 documentos está fallando.

#### Panel 3: "Costo vs Tiempo de Extracción" (Rendimiento)
Cruza el uso de recursos con el tiempo que tarda tu código.
* **Línea A (RAM del Worker):** `process_resident_memory_bytes{kubernetes_pod_name=~"worker-deployment.*"}`
* **Línea B (Tiempo de extracción):** Calcular el percentil 95 (P95) usando tu histograma: 
  `histogram_quantile(0.95, sum(rate(bmo_extraction_duration_seconds_bucket[5m])) by (le))`
* *Diagnóstico:* Te permite ver si los documentos pesados (que disparan la Línea B) también están a punto de agotar la RAM de tu pod (Línea A).

---

Con esto, tienes las herramientas para pasar de ver "números sueltos" a tener un centro de control real. 

¿Te gustaría que te pase directamente el código JSON de un Dashboard pre-armado de Grafana que lea estas métricas específicas de tu proyecto para que solo tengas que darle a "Importar"?