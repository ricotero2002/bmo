# Fase 4: Orquestación Agéntica y Persistencia

## Qué se implementó en esta fase

---

## 1. Metadatos y Deduplicación de Documentos

### ¿Cómo funciona el `file_hash`?

Al subir un archivo, el orquestador calcula el SHA-256 del contenido antes de procesarlo:

```
UPLOAD (bytes) → SHA-256 hash → ¿existe en StatusProvider? 
  SÍ → retorna {"status": "already_exists"}
  NO → procesa normalmente y guarda el hash
```

### Metadatos en cada chunk (ChromaDB / OpenSearch)

Cada chunk indexado tiene:
```json
{
  "source": "informe.pdf",
  "file_hash": "abc123...",
  "created_at": "2026-03-13T18:00:00+00:00",
  "page_number": 2,
  "chunk_index": 4,
  "user_id": "user_123"
}
```

### `source_id_key` y actualizaciones

El `SQLRecordManager` usa `source_id_key="source"` (el nombre del archivo). Esto significa:
- **Archivo idéntico subido de nuevo** → `file_hash` lo detecta → skip total
- **Archivo modificado subido de nuevo** → hash distinto → pasa el check → el `RecordManager` elimina los chunks viejos del `source` y agrega los nuevos (`cleanup="incremental"`)

---

## 2. Alembic — Migraciones de Base de Datos

### Estructura creada

```
alembic/
├── env.py              ← Integra los modelos SQLAlchemy, lee vars de entorno
├── script.py.mako
└── versions/
    └── 001_add_file_hash_to_ingestion_jobs.py
alembic.ini             ← Configuración principal
```

### Comandos principales

```bash
# Primera vez: aplicar todas las migraciones
alembic upgrade head

# Ver estado actual
alembic current

# Ver historial
alembic history --verbose

# Después de cambiar un modelo SQLAlchemy (ej: agregar columna)
alembic revision --autogenerate -m "descripcion del cambio"
alembic upgrade head

# Deshacer la última migración
alembic downgrade -1

# Generar SQL sin aplicarlo (para revisión)
alembic upgrade head --sql
```

### Variables de entorno que usa Alembic

`env.py` lee las mismas variables que ya tenés:

| Variable | Local | Producción (RDS) |
|---|---|---|
| `POSTGRES_USER` | `user` | usuario RDS |
| `POSTGRES_PASSWORD` | `password` | password RDS |
| `DB_HOST` | `localhost` | endpoint RDS |
| `DB_PORT` | `5432` | `5432` |
| `POSTGRES_DB` | `record_manager` | nombre DB RDS |

> **Para producción**: no cambiás código, solo las variables de entorno.

---

## 3. Providers de Producción AWS

### Stack local vs. AWS

| Provider | Local | Producción (AWS) | Free Tier |
|---|---|---|---|
| **Vector Store** | ChromaDB (Docker) | OpenSearch | ⚠️ No free tier |
| **Storage** | MinIO (Docker) | **S3** | ✅ 5GB + 20K GETs |
| **Cache** | Redis (Docker) | **DynamoDB** | ✅ 25GB + 200M requests |
| **Checkpointer LangGraph** | PostgreSQL (Docker) | **RDS PostgreSQL** | ✅ 750 hs t3.micro / 12 meses |
| **Status DB** | PostgreSQL (Docker) | **RDS PostgreSQL** (mismo) | ✅ compartido |
| **Record Manager** | PostgreSQL (Docker) | **RDS PostgreSQL** (mismo) | ✅ compartido |

> `checkpointer`, `database` y `record_manager` comparten la **misma instancia RDS**. Solo cambia `DB_HOST`.

### Variables de entorno AWS (agregar a `.env.production`)

```bash
APP_ENV=production

# Credenciales (o usar IAM Role en ECS — recomendado)
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=us-east-1

# S3
AWS_S3_BUCKET=bmo-documents

# OpenSearch
AWS_OPENSEARCH_URL=https://...us-east-1.es.amazonaws.com
AWS_OPENSEARCH_INDEX=bmo-documents

# DynamoDB
AWS_DYNAMODB_TABLE_CACHE=bmo-cache
AWS_DYNAMODB_TABLE_CHECKPOINTER=bmo-checkpoints

# RDS PostgreSQL (mismo para checkpointer, status_provider y record_manager)
DB_HOST=bmo-db.xxxx.us-east-1.rds.amazonaws.com
POSTGRES_USER=bmo_user
POSTGRES_PASSWORD=...
POSTGRES_DB=bmo_db
```

### Dependencias adicionales para producción

```bash
pip install boto3 requests-aws4auth opensearch-py
```

---

## 4. Evolución del Agente: Seguridad, Metadatos y Control de Alucinaciones

A lo largo de la Fase 4, se consolidó la arquitectura del agente para hacerla más robusta, segura y contextualmente consciente.

### Retriever Unificado y Seguridad (RunnableConfig)

Se eliminó la duplicación de tools (previamente había dos retrievers). Ahora existe un **único retriever unificado** (`knowledge_base_retriever`). 

Para evitar que el LLM tenga control sobre la segmentación de datos por usuario (y prevenir que halucine consultando datos de otro usuario), se implementó la inyección del `user_id` a través de `RunnableConfig`. El LLM desconoce este parámetro; la configuración viaja a nivel de infraestructura transparente hacia la tool.

### Inyección de Tiempo y Filtrado de Fechas

El modelo ahora sabe qué día es en la vida real. El promt (`rag_v2/system.jinja2`) recibe la variable `{{ today }}` en formato ISO `YYYY-MM-DD`.
Cuando el usuario pregunta por "hoy", "ayer" o "este mes", el modelo mismo se encarga de calcular la fecha de corte ISO correspondiente y la envía a la tool a través del parámetro opcional `date_from`.

> **Importante para ChromaDB**: El motor ChromaDB requiere que las fechas se comparen matemáticamente (float). Por lo tanto, el pipeline de Ingestión (`ingestion.py`) guarda el campo `created_at` como Unix Timestamp numérico, y la tool `metadata_filter.py` convierte el string devuelto por el LLM a ese mismo formato para la consulta `$gte`.

### Control de Errores y Retries Agotados vía `Command`

Se implementó un flujo robusto en LangGraph (`agent.py`) para lidiar con errores técnicos de contexto y búsquedas fallidas persistentes:

1. **Guardia Previa en la Tool:** Si la base devuelve error por un `query` vacío, la tool no falla silenciosamente, sino que retorna una cadena con el prefijo `ERROR_TOOL:`.
2. **Reintento Inmediato (`Command`):** El nodo de evaluación (`_grade_documents`) detecta ese prefijo *antes* de calificar relevancia e interrumpe el flujo, enviando un `Command(goto='agent')` para forzar al LLM a que corrija la query inmediatamente.
3. **Manejo de Respuestas Fallidas (Exhausted Retries):** Si las búsquedas legítimas agotan los `MAX_RETRIES` permitidos (porque el documento no existe o no responde a la pregunta), el flujo no deja al agente "a ciegas". Un `Command` emite una orden explícita al agente: *se informa que no existen datos y ordena preguntarle directamente al usuario por más contexto*. Esto erradicó el comportamiento donde el agente devolvía mensajes vacíos o ignoraba la falta de conocimiento.

---

## 5. Pendiente (Fase 5 y Evaluación)

- Cambiar la API para que devuelva el texto en formato **stream**.
- **Evaluación Sistemática del Modelo**: Medir métricas críticas como *Retriever Relevance*, *Faithfulness* (fidelidad a la fuente sin alucinaciones), y *Tool Correctness*.
- Mejorar los tests existentes y agregar **tests de integración end-to-end (E2E)** que cruzen todos los componentes.


# borrado de archivos:
Plantearse cómo borrar datos en un sistema distribuido es de las mejores reflexiones arquitectónicas que puedes hacer. Has tocado uno de los problemas más clásicos de la ingeniería de software: la transaccionalidad distribuida.

Como tienes PostgreSQL, un Vector Store (Redis Stack/Chroma), un Storage (MinIO/S3) y Celery, no puedes usar una transacción SQL normal (COMMIT/ROLLBACK) porque SQL no puede hacer un "rollback" de un archivo que ya borraste en la nube o en la base vectorial.

Para lograr ese efecto de "todo o nada", la industria utiliza un enfoque basado en el Patrón Saga simplificado, utilizando Soft Deletes (Borrado Lógico) + Tareas Asíncronas Idempotentes.

Aquí tienes cómo orquestarlo paso a paso en tu arquitectura actual:


Gatillo: Despachas una tarea a Celery: delete_document_task.delay(doc_id).

Paso 2: La Tarea Asíncrona (Celery Worker)
Aquí es donde ocurre la magia. El worker de Celery toma el doc_id y ejecuta los borrados en un orden específico. La regla de oro aquí es la Idempotencia: si la tarea falla a la mitad y se reintenta, intentar borrar algo que ya se borró no debe lanzar un error, simplemente debe decir "ok, ya no está" y seguir.

El orden de ejecución más seguro en tu DeletionOrchestrator sería:

Vector Store (El más crítico para la IA): Usas el RecordManager de LangChain (o tu implementación) para eliminar los chunks asociados a ese doc_id. Si la IA ya no puede leerlo, el riesgo de fuga de datos desaparece.

Object Storage (MinIO/S3): Borras el PDF/TXT físico del bucket.

Hard Delete (SQL): Una vez que el Vector Store y el Storage confirmaron el borrado, vas a tu PostgreSQL y ahora sí haces un DELETE FROM jobs WHERE doc_id = X (o lo pasas a estado DELETED por temas de auditoría).

Paso 3: Manejo de Errores (El "Rollback" distribuido)
¿Qué pasa si borras el Vector Store, pero MinIO está caído y falla el paso 2?

Como usas Celery, la tarea simplemente fallará y Celery la reintentará en 5 minutos.

En el reintento, el paso 1 (Vector Store) dirá "no encontré los chunks", lo cual está bien (es idempotente), pasa al paso 2, logra borrar en MinIO, y termina en el paso 3.

Si falla definitivamente después de X reintentos, el mensaje se va a tu Dead Letter Queue (DLQ) de RabbitMQ. Desde ahí, puedes tener una alerta para revisarlo manualmente, pero el usuario nunca se vio afectado (porque el archivo sigue oculto por el Soft Delete del Paso 1).


# testear agente

1. Las Métricas Clave (Thresholds)
Para un sistema RAG y un agente, estas son las métricas de DeepEval que necesitas:

Faithfulness (Fidelidad): Mide si la respuesta del LLM se basa estrictamente en el contexto recuperado, sin inventar datos (alucinar). Threshold ideal: 0.85 o superior.

Answer Relevancy: Mide si la respuesta final aborda directamente la pregunta del usuario o si se desvía del tema. Threshold ideal: 0.80.

Nota sobre Contextual Relevancy: Como no tendrás los contenedores levantados, el contexto será estático (mockeado). Por lo tanto, evaluar el Contextual Relevancy no tiene mucho sentido en este paso, ya que eso evalúa al Retriever (la base vectorial), no al LLM.

Gemini said
Implementar evaluaciones automatizadas en el pipeline de CI/CD para un agente de IA es el estándar de oro en LLMOps. Es la única forma de garantizar que un cambio en el prompt o en el modelo no degrade el rendimiento en producción.

Para lograr esto sin necesidad de levantar contenedores locales (como Redis o PostgreSQL), la estrategia es aislar el comportamiento del agente mediante "Mocks". En lugar de que el agente busque en la base de datos real, le inyectamos una herramienta de búsqueda falsa que siempre devuelve el mismo texto. Así, evaluamos puramente la lógica de razonamiento del LLM, el uso de las herramientas y la calidad del prompt.

Aquí tienes cómo estructurar este pipeline de pruebas con DeepEval:

1. Las Métricas Clave (Thresholds)
Para un sistema RAG y un agente, estas son las métricas de DeepEval que necesitas:

Faithfulness (Fidelidad): Mide si la respuesta del LLM se basa estrictamente en el contexto recuperado, sin inventar datos (alucinar). Threshold ideal: 0.85 o superior.

Answer Relevancy: Mide si la respuesta final aborda directamente la pregunta del usuario o si se desvía del tema. Threshold ideal: 0.80.

Nota sobre Contextual Relevancy: Como no tendrás los contenedores levantados, el contexto será estático (mockeado). Por lo tanto, evaluar el Contextual Relevancy no tiene mucho sentido en este paso, ya que eso evalúa al Retriever (la base vectorial), no al LLM.

2. Estructura del Test (PyTest + DeepEval)
Aprovechando que tu arquitectura ya recibe el parámetro prompt_version y las tools de forma inyectable, puedes crear un test que compare dos versiones de prompts en memoria.

Crea un archivo llamado test_agent_evaluation.py:

```python
import pytest
from deepeval import assert_test
from deepeval.test_case import LLMTestCase
from deepeval.metrics import FaithfulnessMetric, AnswerRelevancyMetric
from langchain_core.tools import tool
# Importa tu AgentService y dependencias

from langgraph.checkpoint.memory import MemorySaver

# En tu test:
checkpointer = MemorySaver()
agent_service = AgentService(llm_factory=my_llm_factory, tools=mock_tools, checkpointer=checkpointer)
```
## 1. Mock de la Herramienta (Evita necesitar Redis/Celery)
```python
@tool("knowledge_base_retriever")
def mock_retriever(query: str) -> str:
    """Mock que simula la respuesta de la base de datos vectorial."""
    return "La política de vacaciones de la empresa permite 15 días hábiles al año."

# 2. Configuración del Dataset de Prueba (Golden Dataset)
TEST_CASES = [
    {
        "input": "¿Cuántos días de vacaciones tengo?",
        "expected_output": "Tienes 15 días hábiles al año.",
        "mock_context": ["La política de vacaciones de la empresa permite 15 días hábiles al año."]
    }
]

@pytest.mark.asyncio
@pytest.mark.parametrize("test_data", TEST_CASES)
async def test_agent_rag_quality(test_data):
    # Instanciar el agente inyectando el mock en lugar de la herramienta real
    mock_tools = [mock_retriever]
    agent_service = AgentService(llm_factory=my_llm_factory, tools=mock_tools, checkpointer=my_checkpointer)

    # Definir métricas con thresholds estrictos
    faithfulness_metric = FaithfulnessMetric(threshold=0.85)
    relevancy_metric = AnswerRelevancyMetric(threshold=0.80)

    # 3. Ejecutar el Agente (puedes probar con el prompt actual o uno nuevo)
    result = await agent_service.chat(
        message=test_data["input"],
        thread_id="test_thread_123",
        user_info={"name": "Test User"},
        prompt_version="rag_v2" # Aquí puedes cambiar la versión del prompt a evaluar
    )
    
    actual_response = result["response"]

    # 4. Construir el LLMTestCase de DeepEval
    test_case = LLMTestCase(
        input=test_data["input"],
        actual_output=actual_response,
        expected_output=test_data["expected_output"],
        retrieval_context=test_data["mock_context"] 
    )

    # 5. Ejecutar aserciones (Si no cumple el threshold, el Pull Request fallará)
    assert_test(test_case, [faithfulness_metric, relevancy_metric])
```


3. A/B Testing de Prompts en el Pull Request
La idea de comparar el modelo de prompts anterior con el nuevo es brillante. Como tu función chat ya acepta prompt_version, puedes hacer un script en tu CI/CD que ejecute los mismos TEST_CASES usando prompt_version="rag_v1" y luego prompt_version="rag_v2".

Si rag_v2 obtiene un puntaje de Faithfulness menor que rag_v1 en DeepEval, puedes configurar tu GitHub Actions para que marque una advertencia en el PR ("Degradación de calidad detectada en el prompt").


# Stream
Para lograr esa experiencia moderna donde el usuario ve exactamente qué está pensando el agente y luego ve la respuesta escribirse en tiempo real (como ChatGPT), necesitamos cambiar el enfoque.

Actualmente, tu método `chat` en `agent.py` utiliza `await self.graph.ainvoke(...)`. Esto bloquea la respuesta hasta que el grafo entero termina de ejecutarse. 

Para hacerlo "responsive", vamos a crear un **nuevo endpoint usando Server-Sent Events (SSE)** en FastAPI y aprovecharemos la función `astream_events` de LangGraph. Esto te permitirá enviar al frontend tanto los "estados" (ej. "Buscando en la base de datos...") como los "tokens" (las letras de la respuesta final).

Aquí tienes exactamente los cambios que debes implementar:

### 1. Modificar `agent.py`
Agrega este nuevo método debajo de tu método `chat` actual. Este método usará `astream_events` para emitir todo lo que pasa dentro del grafo paso a paso.

```python
    async def astream_chat(self, message: str, thread_id: str, user_info: dict, prompt_version: str):
        """
        Versión streaming del chat. Emite eventos detallados del grafo usando astream_events.
        """
        user_id = user_info.get("user_id") if user_info else None
        config = {
            "configurable": {
                "thread_id": thread_id,
                "user_id": user_id,
            }
        }

        input_message = {
            "messages": [("user", message)],
            "user_info": user_info,
            "prompt_version": prompt_version,
            "retrieve_retry_count": 0,
            "generate_retry_count": 0,
            "docs_parse_retries": 0,
            "hallucinations_parse_retries": 0
        }

        # version="v2" es el estándar actual recomendado por LangChain para eventos
        async for event in self.graph.astream_events(input_message, config=config, version="v2"):
            yield event
```

### 2. Modificar `endpoints.py`
Vamos a crear un nuevo endpoint `/ask/stream`. Necesitarás importar `StreamingResponse` de FastAPI y `json` para formatear los eventos según el estándar SSE (`text/event-stream`).

Server-Sent Events (SSE) es una tecnología web que permite a un servidor enviar datos e información en tiempo real a un navegador de forma automática, sin que el cliente tenga que solicitarlos constantemente. Utiliza una conexión HTTP estándar y persistente, facilitando actualizaciones unidireccionales (servidor-cliente) ideales para noticias, cotizaciones o notificaciones.

Agrega esto en tu `endpoints.py`:

```python
from fastapi.responses import StreamingResponse
import json

@router.post("/ask/stream")
async def ask_agent_stream(
    request: AskRequest,
    agent_service = Depends(get_agent_service)
):
    """
    Endpoint de streaming. Emite estados (status) y tokens (text) en tiempo real
    usando Server-Sent Events (SSE).
    """
    async def event_generator():
        try:
            user_context = request.user_info or {}
            
            # Llamamos al nuevo método asíncrono que creamos en agent.py
            async for event in agent_service.astream_chat(
                message=request.message, 
                thread_id=request.thread_id,
                user_info=user_context,
                prompt_version=request.prompt_version
            ):
                kind = event["event"]
                
                # 1. Detectar cuando el LLM está transmitiendo la respuesta final
                if kind == "on_chat_model_stream":
                    content = event["data"]["chunk"].content
                    if content:
                        # Enviamos tipo 'token' para que el frontend lo sume al chat
                        yield f"data: {json.dumps({'type': 'token', 'content': content})}\n\n"
                
                # 2. Detectar cuando se llama a una herramienta (Retriever)
                elif kind == "on_tool_start":
                    tool_name = event["name"]
                    if tool_name == "knowledge_base_retriever":
                        yield f"data: {json.dumps({'type': 'status', 'content': 'Buscando en la base de conocimientos...'})}\n\n"
                    else:
                        yield f"data: {json.dumps({'type': 'status', 'content': f'Usando herramienta: {tool_name}...'})}\n\n"
                
                # 3. Detectar nodos de validación (Guardrails/Graders)
                elif kind == "on_chain_start":
                    node_name = event.get("name")
                    if node_name == "grade_documents":
                        yield f"data: {json.dumps({'type': 'status', 'content': 'Evaluando relevancia de los documentos...'})}\n\n"
                    elif node_name == "grade_hallucinations":
                        yield f"data: {json.dumps({'type': 'status', 'content': 'Verificando alucinaciones...'})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
            
    # El media_type es crucial para que el frontend (ej. Vercel AI SDK) lo lea como un stream continuo
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

---

### ¿Cómo funciona esto en la práctica?
Al separar los mensajes en `type: 'token'` y `type: 'status'`, tu frontend puede reaccionar de forma inteligente. Si recibe un `status`, puede mostrar un pequeño indicador de carga con el texto ("Evaluando relevancia de los documentos...") para que el usuario sepa que la IA no se colgó, sino que está trabajando en el fondo. Cuando empieza a recibir `token`, oculta el estado y empieza a renderizar el texto final.

¿Te gustaría que te muestre cómo probar este nuevo endpoint de streaming usando simplemente la terminal (con `curl`) antes de conectarlo a tu frontend de React?


# Cómo testear la Búsqueda (Retriever y Agent Querying)
A. Testear la Inteligencia del Agente (Unit Test del Tool Calling)
Para testear si el agente arma bien la query y usa bien los metadatos (Hybrid Search), puedes hacer que el Mock actúe como un "Espía" (Spy). En lugar de solo devolver texto, el mock valida los parámetros que el LLM le envió.

Python
@tool("knowledge_base_retriever")
def mock_retriever_spy(query: str, user_id: str = None) -> str:
    """Mock que valida si el agente generó los parámetros correctos."""
    
    # 1. Validar que el LLM entendió qué buscar
    assert "vacaciones" in query.lower(), f"El agente generó una mala query: {query}"
    
    # 2. Validar que el LLM extrajo y pasó los metadatos correctos (Hybrid Search)
    assert user_id == "user_123", "El agente no filtró por el ID del usuario correcto"
    
    return "La política de vacaciones permite 15 días hábiles."
Si el LLM alucina la query o ignora los filtros, el assert fallará y el test se rompe. Esto prueba la "Inteligencia" sin depender de una base vectorial.
