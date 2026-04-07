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
`POST /api/feedback
Ver la planificacion en el frontend
Poder acceder como link a las sources del frontend.
No me mostro en el frontend que va a guardar un archivo.
Probar generar el dataset
x No parece estar andando el guardar archivos, nunca se me inician instancias de los kafka consumers, nose si se estan mandando a kafka directamente.
Ver porque hay 2 metricas distintas en grafana de los tokens.


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
