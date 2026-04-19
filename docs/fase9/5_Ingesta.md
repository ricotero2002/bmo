# Ingesta

## Como funciona Spache Airflow y DAG


Para entender Apache Airflow, primero hay que derribar el mito más común: Airflow no procesa datos. No es como Apache Spark. Airflow es el director de orquesta. Su trabajo no es tocar los instrumentos (mover gigabytes de información), sino decirle a cada instrumento (scripts de Python, Spark, dbt, MinIO) cuándo debe tocar, en qué orden, y qué hacer si alguien desafina (manejo de errores y reintentos).

### ¿Qué es un DAG?
DAG significa Directed Acyclic Graph (Grafo Acíclico Dirigido). Es la forma matemática en la que Airflow entiende los flujos de trabajo.

Graph (Grafo): Está compuesto por Nodos (Tareas) y Aristas (Dependencias).

Directed (Dirigido): Tiene una dirección fija. La Tarea B solo se ejecuta después de la Tarea A.

Acyclic (Acíclico): No puede tener bucles infinitos. La Tarea A va a la B, la B a la C, pero la C nunca puede volver a la A. Si lo hiciera, el flujo nunca terminaría.

### Flujo 1: Extracción Incremental y Carga a Raw (Data Lake)
Cuando tienes altos volúmenes de datos (ej. miles de notas de Notion o Obsidian), hacer una copia completa de toda tu base de datos todos los días es ineficiente y costoso. Aquí aplicamos Extracción Incremental (o CDC - Change Data Capture).

Airflow maneja el tiempo de forma especial usando el concepto de Data Intervals (data_interval_start y data_interval_end).

Cómo funciona exactamente:

El Disparador (Scheduler): Airflow despierta todos los días a las 00:00.

La Consulta Inteligente (PythonOperator): Airflow ejecuta una tarea en Python que se conecta a la API de tu fuente (ej. Notion). En lugar de pedir "dame todo", le pasa una fecha: GET /pages?updated_after={{ data_interval_start }}. Así, solo descarga las notas que tú modificaste o creaste en las últimas 24 horas.

Carga a Raw (S3Hook/MinIO): Airflow toma ese JSON resultante (que pesa apenas unos kilobytes o megabytes) y lo sube directamente a tu Data Lake en MinIO, en una ruta particionada por fecha, por ejemplo: s3://raw-zone/notion/year=2026/month=04/day=19/updates.json.

### Flujo 2: Emisión de Eventos ingestion_events y Procesamiento con KEDA
Una vez que el archivo físico está seguro en MinIO (Capa Raw), tu Asistente de IA necesita procesarlo (chunking, vectorización con el LLM, guardar en Pinecone/Postgres). Aquí pasamos de un modelo Batch (Airflow) a un modelo de Streaming y Autoscalado (Kafka + KEDA).

Cómo funciona exactamente:

Paso 1: Airflow emite el evento (El "Aviso")
Agregamos una tercera tarea al DAG de arriba. Una vez que tarea_cargar termina con éxito, Airflow usa un proveedor de Kafka para enviar un mensaje minúsculo a tu tópico ingestion_events.
El mensaje (Payload) no contiene los datos, solo la referencia (Pattern llamado Claim Check):

{
  "event_type": "new_file_raw",
  "source_system": "notion",
  "file_path": "s3://raw-zone/notion/year=2026/month=04/day=19/updates.json"
}

Paso 2: La cola de Kafka crece
Imagina que hoy agregaste 50 archivos distintos. Airflow envía 50 mensajes a Kafka. Estos mensajes se quedan esperando en la cola (esto genera lo que se llama Lag o retraso).

Paso 3: KEDA entra en acción (La Magia de la Escalabilidad)
KEDA (Kubernetes Event-driven Autoscaling) es un vigilante que instalas en tu clúster de Kubernetes (local o cloud).

KEDA observa: KEDA está configurado para mirar constantemente el tópico ingestion_events de Kafka.

KEDA calcula: Ve que el "Lag" subió a 50 mensajes. Tú le configuraste una regla: "Por cada 10 mensajes en cola, levanta 1 Pod (contenedor) de mi Celery Worker".

KEDA escala: KEDA le dice a Kubernetes: "¡Necesitamos poder de cómputo ahora!". Kubernetes levanta instantáneamente 5 réplicas de tus Workers del Asistente IA.

Paso 4: Procesamiento Paralelo

Tus 5 Workers recién nacidos se conectan a Kafka.

1. Cada Worker toma un mensaje distinto al mismo tiempo.

2. Leen la ruta file_path, van a MinIO, descargan el JSON, hacen el Agentic Chunking, llaman a OpenRouter para vectorizar, y guardan los vectores en la base de datos.

3. Hacen un Ack (Acknowledge) a Kafka diciendo: "Mensaje procesado".