¡Llegaste a la fase de madurez! Aquí es donde tu asistente deja de ser un "proyecto de fin de semana" y se convierte en un producto de software robusto, medible y escalable.

Implementar "Human in the Loop" (HITL), Testing con Golden Datasets y Análisis de Telemetría es lo que define a los sistemas de IA empresariales (LLMOps).

Vamos a armar un plan estructurado para abordar los Pasos 4.2 y 4.3, integrando las métricas de rendimiento y costos que mencionaste.

---

### Plan de Implementación: Fase 4 (LLMOps, Calidad y Telemetría)

Este plan se divide en tres frentes de trabajo: **Interacción de Usuario (Feedback)**, **Testing Automatizado (Calidad)** y **Monitoreo/Carga (Infraestructura)**.

#### Frente 1: "Human in the Loop" (Feedback Loop)

El objetivo es capturar cuándo el modelo acierta y cuándo se equivoca, directamente desde la experiencia del usuario.

**Paso 1: Diseño de la Base de Datos (PostgreSQL)**
Necesitamos una tabla para almacenar las interacciones y el feedback.
* **Tabla `chat_feedback`:**
    * `id` (UUID)
    * `thread_id` (String - Para enlazar con la conversación)
    * `user_prompt` (Text - Lo que preguntó el usuario)
    * `ai_response` (Text - Lo que respondió BMO)
    * `retrieved_context` (JSONB - Los chunks exactos que usó el LLM)
    * `score` (Int: 1 para 👍, -1 para 👎)
    * `user_correction` (Text - Opcional, si el usuario escribe cuál debió ser la respuesta)
    * `timestamp` (DateTime)

    mas que retrieved_context deberia indicar que tools se usaron, que se trajo (web o source), porque quizas el problema es que no guardno nada o cosas asi, agregar que cuando use la tool guardar devuelva una notificacion o algo asi indicando el id del nuevo archivo y nombre junto ocn un seguimiento del mismo.

    Para esto usar alembic

**Paso 2: Endpoint de Feedback en la API (FastAPI)**
* Crear un endpoint `POST /api/feedback` que reciba el `thread_id`, el ID del mensaje específico y el `score` (con la corrección opcional).
* Este endpoint guardará el registro en la tabla `chat_feedback` utilizando SQLAlchemy.

**Paso 3: Integración en el Frontend**
* Modificar la UI del chat para que cada burbuja de respuesta del Agente tenga los botones 👍 y 👎.
* Si el usuario presiona 👎, mostrar un pequeño modal: "¡Ups! ¿Cómo debería haber respondido BMO? Falto que realizara alguna accion?".
* Enviar esta información al nuevo endpoint `/api/feedback`.
Para esto crear un componente para los botones que use la imagen, la api route (que sea del lado del servidor para mandar el mensaje) y en services/api la funcion para llamar a la api 

Tambien hay que agregar un modal en el llm que cuando se llame al guardar documento se le muestre su id para que el pueda ir siguiendo la subida del archivo.
Aparte ahora como hay una planificacion estaria bueno poder mostrarsela al usuario junto con el probreso de la misma, que se pueda apliar o mostrar el actual, arriba de los mensajes etereos.

#### Frente 2: Testing Automatizado con Golden Datasets (LLM-as-a-Judge)

Aquí usaremos los datos recolectados (y los generados sintéticamente) para asegurar que el agente no empeore con futuras actualizaciones de código o prompts.

**Paso 1: Construcción del Golden Dataset**
* Crear un script (ej. `scripts/export_golden_dataset.py`) que extraiga de la base de datos las filas de `chat_feedback` donde `score == 1` o donde exista un `user_correction` válido.
* Guardar esto en un archivo (ej. `golden_dataset.json` o `.csv`) con la estructura: `[{"query": "...", "expected_response": "..."}]`. (Aprovechar el que ya existe tambien)
Ademas hay que sumarle los dataset de /evals/golden_dataset_v2

Que esto se haga en golden_dataset_v2 convinando ambos tipos. Que use el database provider para no tener problemas segun donde se este testeando.

**Paso 2: Implementación de la Suite de Evaluación (Pytest + LangChain)**
* Crear una suite `tests/evaluations/test_rag_quality.py`.
* Usar la técnica **"LLM-as-a-Judge"**. En lugar de comparar textos exactamente (lo cual fallará porque los LLMs varían sus palabras), usarás otro modelo (ej. Gemini Pro o GPT-4, configurado con `temperature=0`) para que actúe como juez.
* **Prompt del Juez:**
    *"Eres un evaluador imparcial. Compara la RESPUESTA_ACTUAL con la RESPUESTA_ESPERADA basándote en la PREGUNTA_DEL_USUARIO. Evalúa la precisión semántica y fáctica. Responde únicamente 'PASS' si la RESPUESTA_ACTUAL contiene la información clave de la RESPUESTA_ESPERADA, o 'FAIL' si contradice o ignora información vital."*

Para esto se puede usar la base de los tests ya existentes.

**Paso 3: Ejecución de Regresiones (CI/CD)**
* Configurar tu pipeline (ej. GitHub Actions) para que corra este script de evaluación cada vez que modifiques los prompts (`prompts.py`), las herramientas o la lógica de ruteo en LangGraph.








PS C:\Users\Agustin\Desktop\Agustin\personal-ai-assistant> kubectl logs -n personal-ai -l app=kafka-consumer --follow
>> 
/usr/local/lib/python3.12/site-packages/pydub/utils.py:170: RuntimeWarning: Couldn't find ffmpeg or avconv - defaulting to ffmpeg, but may not work
  warn("Couldn't find ffmpeg or avconv - defaulting to ffmpeg, but may not work", RuntimeWarning)
INFO:src.providers.storage.oci_storage_provider:OCIStorageProvider iniciado — endpoint: https://id4tvhmgtjrz.compat.objectstorage.us-ashburn-1.oraclecloud.com, bucket: bmo-documents
INFO:__main__:Conectando a Kafka: kafka-bmo-bmo.l.aivencloud.com:23658 (env=production)
INFO:__main__:Consumidor Kafka iniciado. Escuchando tópico: raw-documents
INFO:__main__:Conectando a Kafka: kafka-bmo-bmo.l.aivencloud.com:23658 (env=production)
INFO:__main__:Consumidor Kafka iniciado. Escuchando tópico: raw-documents
WARNING:src.providers.storage.oci_storage_provider:--- DEBUG OCI: test_routing_user/37b19b72-a229-42c6-9873-40c31bf05e0e (bytes size: 316) ---
WARNING:src.providers.storage.oci_storage_provider:Éxito: oci://bmo-documents/test_routing_user/37b19b72-a229-42c6-9873-40c31bf05e0e (316 bytes)
WARNING:celery.backends.redis:
Setting ssl_cert_reqs=CERT_NONE when connecting to redis means that celery will not validate the identity of the redis broker when connecting. This leaves you vulnerable to man in the middle attacks.

INFO:src.service.orchestrator:Job previo 89993734-0d58-4841-b919-2bcaddc02350 en estado 'dead'. Reintentando con el mismo doc_id.
WARNING:src.providers.storage.oci_storage_provider:--- DEBUG OCI: test_routing_user/89993734-0d58-4841-b919-2bcaddc02350 (bytes size: 329) ---
WARNING:src.providers.storage.oci_storage_provider:Éxito: oci://bmo-documents/test_routing_user/89993734-0d58-4841-b919-2bcaddc02350 (329 bytes)
INFO:src.service.orchestrator:Job previo d06dee67-1f7e-458c-902f-c6cf8663b02f en estado 'dead'. Reintentando con el mismo doc_id.
WARNING:src.providers.storage.oci_storage_provider:--- DEBUG OCI: test_routing_user/d06dee67-1f7e-458c-902f-c6cf8663b02f (bytes size: 295) ---
WARNING:src.providers.storage.oci_storage_provider:--- DEBUG OCI: test_routing_user/b2029bcb-8760-4685-82e7-b2943243cb41 (bytes size: 326) ---
WARNING:src.providers.storage.oci_storage_provider:Éxito: oci://bmo-documents/test_routing_user/d06dee67-1f7e-458c-902f-c6cf8663b02f (295 bytes)
WARNING:src.providers.storage.oci_storage_provider:Éxito: oci://bmo-documents/test_routing_user/b2029bcb-8760-4685-82e7-b2943243cb41 (326 bytes)
WARNING:celery.backends.redis:
Setting ssl_cert_reqs=CERT_NONE when connecting to redis means that celery will not validate the identity of the redis broker when connecting. This leaves you vulnerable to man in the middle attacks.

INFO:src.service.orchestrator:Job previo 077cef7a-3590-4c6a-8891-ba82d3465e0e en estado 'dead'. Reintentando con el mismo doc_id.
WARNING:src.providers.storage.oci_storage_provider:--- DEBUG OCI: test_routing_user/077cef7a-3590-4c6a-8891-ba82d3465e0e (bytes size: 314) ---
WARNING:src.providers.storage.oci_storage_provider:Éxito: oci://bmo-documents/test_routing_user/077cef7a-3590-4c6a-8891-ba82d3465e0e (314 bytes)
WARNING:src.providers.storage.oci_storage_provider:--- DEBUG OCI: test_routing_user/a3318083-6d9c-4183-9b0f-d4442f0009a4 (bytes size: 385) ---
WARNING:src.providers.storage.oci_storage_provider:Éxito: oci://bmo-documents/test_routing_user/a3318083-6d9c-4183-9b0f-d4442f0009a4 (385 bytes)

# Falta


x Poner fecha al subir archivos en el frontend
x poder ver sus chunking y el archivo
x POST /api/feedback
x No parece estar andando el guardar archivos, nunca se me inician instancias de los kafka consumers, nose si se estan mandando a kafka directamente.


#### Frente 3: Telemetría, Costos y Pruebas de Estrés (Observabilidad)

Aprovechando que ya tienes OpenTelemetry, Prometheus y Grafana configurados, vamos a crear los dashboards necesarios.

**Paso 1: Trazas de Latencia (OpenTelemetry)**
* **Latencia de Ingesta:** Asegúrate de que tu worker de Celery (`tasks.py`) tenga un *Span* de OpenTelemetry que envuelva la función `process_document`. Podrás ver en Jaeger o Grafana Tempo cuánto toma el proceso completo (Chunking -> Embedding -> Pinecone).
* **Latencia Vectorial:** Crea un *Span* específico alrededor de la llamada a `_vector_store.similarity_search` o `compression_retriever.invoke` en tu tool `web_search.py`.
* **TTFT (Time-to-First-Token):** Esto es crucial. Mide el tiempo en tu endpoint de streaming (FastAPI) desde que recibes el request hasta que emites el primer chunk `yield` hacia el cliente. Registra esta métrica en Prometheus (`prometheus_client.Summary` o `Histogram`).

**Paso 2: Monitoreo de Costos (Tokens)**
* LangChain ya expone metadatos de uso (`usage_metadata`).
* En tu clase `AgentService`, intercepta la respuesta final del LLM, extrae los `input_tokens` y `output_tokens`, y regístralos en un contador de Prometheus (ej. `llm_tokens_total{model="gemini-flash", type="input"}`).
* En Grafana, crea un panel que multiplique estos contadores por el precio actual del API por cada 1K tokens para tener un estimado de gasto en tiempo real.

(Esto creo que no esta funcionando)

**Paso 3: Pruebas de Estrés y Autoescalado**
* **Herramienta de Carga:** Usa **Locust** o **K6** (escritos en Python/JS) para simular tráfico. Crea un script `locustfile.py` que envíe preguntas concurrentes al endpoint del chat.
* **Prueba de Ingesta Masiva:** Simula la subida de 50 PDFs simultáneos a tu API y observa cómo la cola de Kafka/Celery crece.
* **Validación de KEDA/HPA:** Mientras ejecutas Locust, abre `k9s` o el dashboard de Kubernetes. Observa si, al subir la CPU de los workers o el lag de Kafka, Kubernetes despliega nuevos Pods automáticamente para manejar la carga, y cómo se reduce a 1 Pod (o 0 si usas scale-to-zero con KEDA) cuando la prueba termina.


¡Excelente iniciativa! Pasar a la fase de pruebas de estrés y monitoreo es el paso definitivo para graduar tu arquitectura a nivel "producción real". Además, como veo en tu captura de LangSmith, ya estás trackeando tokens, latencia y costos perfectamente, lo cual nos facilita mucho el trabajo.

Aquí tienes el plan de acción completo, estructurado desde la instrumentación hasta la ejecución y medición con **Locust**, **LangSmith** y **Kubernetes**.

---

### Paso 1: Etiquetado (Tagging) para LangSmith

Para no ensuciar tus métricas de uso real con miles de peticiones de prueba, necesitamos "etiquetar" las ejecuciones de estrés. LangSmith permite filtrar todo por `tags` o `metadata`.

**Modificación en `agent.py`:**
Cuando llames a `astream_events` o `ainvoke`, inyecta un tag dinámico. Puedes modificar tu endpoint en `endpoints.py` para que acepte un header oculto (ej. `X-Stress-Test: true`) y pasarlo al agente.

```python
# En agent.py (dentro de astream_chat)
tags = ["agent_generation"]
if user_info.get("is_stress_test"):
    tags.append("stress_test_v1") # <-- Etiqueta clave para LangSmith

config = {
    "configurable": {
        "thread_id": thread_id,
        "user_id": user_id,
    },
    "tags": tags,
    "metadata": {"test_type": "load_test"}
}
```

---

### Paso 2: Crear el Script de Locust (`locustfile.py`)

Locust es ideal porque te permite escribir los flujos en Python puro. Vamos a crear un script que simule dos perfiles de usuarios: **Chatters** (piden respuestas por streaming) e **Ingestors** (suben PDFs).

Instala Locust y la librería para eventos (SSE):
`pip install locust sseclient-py`

Crea este archivo `locustfile.py`:

```python
import time
import json
import uuid
from locust import HttpUser, task, between, events

class BMOUser(HttpUser):
    wait_time = between(1, 3) # Espera entre 1 y 3 segundos entre tareas
    host = "http://localhost:8000" # Cambia por tu Ingress URL si estás en k8s

    @task(3) # Peso 3: Es 3 veces más probable que un usuario chatee a que suba un PDF
    def chat_streaming(self):
        thread_id = str(uuid.uuid4())
        payload = {
            "message": "Resume los puntos clave del documento subido.",
            "thread_id": thread_id,
            "prompt_version": "rag_v3",
            "user_info": {"user_id": "locust_tester", "is_stress_test": True}
        }
        
        start_time = time.time()
        ttft_recorded = False

        # Usamos stream=True para capturar los chunks en tiempo real
        with self.client.post("/api/ask/stream", json=payload, stream=True, catch_response=True) as response:
            if response.status_code == 200:
                for line in response.iter_lines():
                    if line:
                        decoded_line = line.decode('utf-8')
                        
                        # Capturar TTFT (Time To First Token)
                        if not ttft_recorded and '"type": "token"' in decoded_line:
                            ttft = time.time() - start_time
                            events.request.fire(
                                request_type="SSE",
                                name="TTFT",
                                response_time=ttft * 1000,
                                response_length=0,
                            )
                            ttft_recorded = True

                        if "[DONE]" in decoded_line:
                            break
                            
                # Registrar el tiempo total (Latencia de Respuesta Completa)
                total_time = time.time() - start_time
                events.request.fire(
                    request_type="SSE",
                    name="Total Chat Time",
                    response_time=total_time * 1000,
                    response_length=0,
                )
                response.success()
            else:
                response.failure(f"Error {response.status_code}")

    @task(1) # Peso 1: Tarea de ingesta masiva
    def upload_document(self):
        # Crear un archivo PDF falso en memoria para no saturar tu disco
        dummy_pdf_content = b"%PDF-1.4\n%Fake PDF content for stress testing...\n%%EOF"
        files = {
            'file': ('test_doc.pdf', dummy_pdf_content, 'application/pdf')
        }
        data = {
            'user_id': 'locust_tester',
            'document_date': '2026-04-07'
        }
        
        with self.client.post("/api/ingest", files=files, data=data, catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Ingest Failed: {response.text}")
```

---

### Paso 3: Ejecución y Validación de KEDA/HPA

Abre tres terminales para tener visibilidad total:

**Terminal 1 (Lanzar el ataque con Locust):**
```bash
locust -f locustfile.py
```
Abre tu navegador en `http://localhost:8089`. Configura **50 usuarios concurrentes** con un spawn rate de **5 usuarios por segundo**. Inicia la prueba.

**Terminal 2 (Monitor de Kubernetes - Pods):**
Para ver en tiempo real cómo Kubernetes reacciona a la CPU y la cola de Kafka:
```bash
kubectl get pods -n personal-ai -w
```
*Deberías empezar a ver Pods de `api-deployment` y `worker-deployment` pasando a estado `ContainerCreating` a medida que la carga aumenta.*

**Terminal 3 (Monitor de Kafka/KEDA):**
KEDA lee el lag de Kafka para escalar los workers. Puedes monitorear el HPA (Horizontal Pod Autoscaler) generado por KEDA:
```bash
kubectl get hpa -n personal-ai -w
```
*Verás el campo `TARGETS` subir (ej. `500/100` mensajes de lag) y la columna `REPLICAS` escalar de 1 a 5, 10, etc.*

---

### Paso 4: ¿Dónde y Cómo Medir cada Métrica?

#### 1. TTFT (Time To First Token) y Tiempo Total
* **Dónde medirlo:** En la interfaz web de Locust (`http://localhost:8089`).
* **Cómo leerlo:** En la pestaña "Statistics", verás dos filas personalizadas llamadas `SSE TTFT` y `SSE Total Chat Time`. Locust te dará el promedio, el percentil 95 y el máximo bajo carga extrema.

#### 2. Latencia Vectorial (Pinecone) y Costos
* **Dónde medirlo:** En tu dashboard de **LangSmith**.
* **Cómo leerlo:** 1. Ve a LangSmith y usa el filtro de búsqueda: `has_tag("stress_test_v1")`.
    2. Como se ve en tu captura, las columnas **Tokens** y **Cost** te darán el gasto exacto de la prueba de estrés.
    3. Para la *Latencia Vectorial*, haz clic en cualquier ejecución del test. Busca en el árbol de ejecución el nodo correspondiente a `knowledge_base_retriever` o `grade_documents`. El tiempo marcado a la derecha de ese nodo específico es tu latencia neta de Pinecone + Red.

#### 3. Latencia de Ingesta (El viaje completo)
* **Dónde medirlo:** En los dashboards de Grafana/Prometheus o en tu base de datos SQL (`status_provider`).
* **Cómo leerlo:** Dado que en tu archivo `kafka_consumer.py` ya configuraste OpenTelemetry y un exportador de métricas (`celery-exporter`), puedes armar un panel en Grafana que mida la diferencia de tiempo entre que el API emite la métrica `docs_processed` con status "ingesting" y el worker emite la métrica final "kafka_success". 
* **Alternativa SQL:** Tu `status_provider` guarda los estados. Puedes hacer un script post-prueba que consulte la tabla de ingestas y calcule: `promedio(updated_at - created_at) donde status = 'completed' y user_id = 'locust_tester'`.


Tuve probelmas con la saturazion entonces hice cambios
Mejoras de Arquitectura
1. Servidor de Producción (Gunicorn)
Dockerfile
: Se ha actualizado el comando de inicio para la API de producción. Ahora utiliza Gunicorn con workers de Uvicorn, lo que permite manejar múltiples peticiones en paralelo aprovechando todos los núcleos del procesador.
2. Pool de Conexiones a Base de Datos
core.py
: Se han configurado parámetros profesionales en SQLAlchemy para evitar cuellos de botella en la base de datos:
pool_size=20: Mantiene 20 conexiones abiertas listas para usar.
max_overflow=10: Permite hasta 10 conexiones adicionales durante picos de tráfico.
pool_timeout=30: Evita errores inmediatos si la base de datos está temporalmente saturada.
3. Escalado Proactivo (K8s)
api-hpa.yaml
: Se redujo el umbral de CPU del 70% al 60%. Esto hace que Kubernetes levante nuevas réplicas de forma más agresiva, antes de que los Pods existentes se saturen.
apps-deployment.yaml
: Se añadió --prefetch-multiplier=1 al comando del worker de Celery para prevenir errores de memoria (OOM) durante el procesamiento de múltiples documentos pesados.

# Para luego 
Ver la planificacion en el frontend
Poder acceder como link a las sources del frontend.
No me mostro en el frontend que va a guardar un archivo.
Ver los modelos de los llms en grafana
Arreglar el kafka producer usado para guardar archivos:
  %3|1775573645.546|SSL|rdkafka#producer-1| [thrd:app]: kafka: error:12800067:DSO support routines::could not load the shared library: filename(/usr/lib64/ossl-modules/legacy.so): /usr/lib64/ossl-modules/legacy.so: cannot open shared object file: No such file or directory
%3|1775573645.546|SSL|rdkafka#producer-1| [thrd:app]: kafka: error:12800067:DSO support routines::could not load the shared library
Error al publicar nota en Kafka: KafkaError{code=_INVALID_ARG,val=-186,str="Failed to create producer: Failed to load OpenSSL provider "legacy": error:07880025:common libcrypto routines::reason(524325): name=legacy"}
INFO:     10.42.0.100:42650 - "GET /api/chats?user_id=agustin HTTP/1.1" 200 OK
INFO:     10.42.0.100:34130 - "GET /api/chats/05f023ba-9e70-4adc-8fb4-cdff087f94da/messages HTTP/1.1" 200 OK
