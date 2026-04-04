# Fase 7 — Parte 3: Expansión de Herramientas y System Prompt Avanzado

## Resumen

Esta parte implementa la capa de herramientas del agente BMO, llevándolo de ser un simple buscador a un orquestador inteligente capaz de:
1. **Buscar en internet** como fallback cuando la base local no tiene respuesta.
2. **Guardar notas** persistentes en la base de conocimientos desde el chat.
3. **Citar siempre sus fuentes** con links clickeables (Presigned URLs para docs locales, URLs directas para web).
4. **Encadenar herramientas** en consultas complejas multi-salto (local → web → síntesis).

---

## Archivos Creados / Modificados

### Infraestructura Kafka (nueva)

| Archivo | Descripción |
|---------|-------------|
| `src/providers/messaging/__init__.py` | Package de providers de mensajería |
| `src/providers/messaging/kafka_config.py` | `build_kafka_conf()` — lógica TLS/SASL unificada para local y Aiven |
| `src/providers/messaging/kafka_producer.py` | `KafkaProducerWrapper` — singleton para publicación fire-and-forget |
| `src/workers/kafka_consumer.py` | **Refactorizado** para usar `build_kafka_conf()` del provider compartido |

### Herramientas del Agente

| Archivo | Descripción |
|---------|-------------|
| `src/tools/web_search.py` | Tool DuckDuckGo — búsqueda web estructurada |
| `src/tools/save_note.py` | Tool Kafka — guarda notas en la base de conocimientos |
| `src/tools/metadata_filter.py` | **Modificado** — agrega Presigned URL por cada resultado devuelto |
| `src/tools/registry.py` | **Modificado** — registra `web_search` y `save_note_to_knowledge_base` |

### System Prompt (rag_v3)

| Archivo | Descripción |
|---------|-------------|
| `src/core/prompts/rag_v3/system.jinja2` | Nuevo system prompt con 5 instrucciones críticas y `{{ few_shots }}` |
| `src/core/prompts/rag_v3/grader_document.jinja2` | Grader de relevancia (copiado de rag_v2) |
| `src/core/prompts/rag_v3/grader_hallucination.jinja2` | Grader de alucinaciones (copiado de rag_v2) |
| `src/core/prompts/agent_few_shots.py` | `AGENT_FEW_SHOTS` — ejemplos desacoplados del template |
| `src/core/prompts/__init__.py` | **Modificado** — exporta `AGENT_FEW_SHOTS` |
| `src/service/prompt_loader.py` | **Modificado** — default a `rag_v3`, pre-renderiza `few_shots` en load time |

### Tests

| Archivo | Tipo | Descripción |
|---------|------|-------------|
| `src/tests/unit/test_new_tools.py` | **Unit** | `web_search` y `save_note` aislados con mocks — sin internet ni Kafka real |
| `src/tests/integration/test_tools_live.py` | **Live Tool** | Búsqueda real en internet (DuckDuckGo) y validación de formato |
| `src/tests/agente/test_tool_routing.py` | **Integración** | Enrutamiento de tools: 3 single-tool + 1 multi-tool con seed de datos |

---

## Flujo de `save_note_to_knowledge_base`

```
AgentService.chat()
    └─ save_note_to_knowledge_base(title, content, doc_type)
           └─ KafkaProducerWrapper.get_instance().produce(
                  topic="raw-documents",
                  key=doc_id,
                  value=JSON_payload
              )
                  └─ kafka_consumer.py: run_consumer()
                         └─ IngestionOrchestrator.orchestrate_ingestion(...)
                                └─ StorageFactory.upload_file(...)
                                └─ Celery: process_document_task(...)
                                       └─ Chunking → Embeddings → Pinecone
```

**Payload Kafka (compatible con `kafka_consumer.py` sin cambios):**
```json
{
  "doc_id": "uuid",
  "filename": "agent_notes/slug_YYYYMMDD_HHMMSS.md",
  "user_id": "user_id_del_config",
  "content": "# Título\n\nContenido markdown...",
  "metadata": {
    "source": "agent_notes/...",
    "doc_type": "general",
    "title": "Título",
    "created_at": "ISO timestamp",
    "origin": "bmo_agent_generated"
  }
}
```

---

## Dependencias Nuevas

```bash
# Ya agregadas a requirements/base.txt:
duckduckgo-search>=6.0.0
jinja2>=3.0.0
```

---

## Cómo Ejecutar los Tests

### Unit Tests (sin dependencias externas — rápidos)

Prueban `web_search` y `save_note` de forma aislada con mocks. No requieren Kafka, internet ni VectorDB.

```bash
python -m pytest src/tests/unit/test_new_tools.py -v
```

Qué cubre:
- `web_search`: formato de output, truncación de snippets a 800 chars, resultados vacíos, fallback a texto plano, manejo de excepciones, link `#` por defecto.
- `save_note`: payload compatible con `kafka_consumer.py`, contenido en Markdown, filename en `agent_notes/*.md`, `origin=bmo_agent_generated`, key de Kafka == doc_id, comportamiento sin config/user_id.

### Tests de Integración Live (Requieren internet/servicios)

#### 1. Live Tool Test (Solo la herramienta, sin el agente)
Prueba que DuckDuckGo responda correctamente y que el parseo sea válido con acceso real a internet.

```bash
python -m pytest src/tests/integration/test_tools_live.py -v -s
```

#### 2. Agent Routing (El agente tomando decisiones)

```bash
# Enrutamiento de tools con agente real (incluye test multi-tool con seed)
python -m pytest src/tests/agente/test_tool_routing.py -v -s

python -m pytest src/tests/agente/test_tool_routing.py -k "save_note_to_knowledge_base" -v -s

# Regresión completa del agente (no debe romper nada)
python -m pytest src/tests/agente/ -v -s

# Golden Dataset (Parte 2 — regresión)
python -m pytest src/evals/test_rag_agentic.py -v -s
```

---

## Pendientes


---

## Sesión de Optimización (Fase 7 — Parte 3)

### 1. Cambios Implementados en la Sesión

#### 1.1 Deep Search — `src/tools/web_search.py`
La herramienta `web_search` evolucionó de un buscador de snippets a un **scraper activo**:
- Usa `requests` + `BeautifulSoup` para extraer hasta **4000 caracteres** de texto real de las páginas.
- Aplica scraping profundo a los **2 primeros resultados**.
- Fallback automático al snippet si hay errores de acceso.

#### 1.2 Ruteo Inteligente Post-Herramienta — `src/service/agent.py`
Se implementó `_route_after_tools` para distinguir entre:
- **Herramientas de recuperación** (`knowledge_base_retriever`, `web_search`) → van a `grade_documents`.
- **Herramientas de acción** (`save_note_to_knowledge_base`, `get_weather`) → vuelven al `agent`.

#### 1.3 Router del Agente como Nodo
`_agent_router` se registró como un **nodo del grafo**. Esto permite devolver objetos `Command` para realizar "nudges" (empujoncitos) al agente cuando devuelve respuestas vacías o incompletas.

#### 1.4 Mecanismo de "Nudge"
Si el agente no genera contenido tras una recuperación exitosa, se inyecta un mensaje de sistema forzando la síntesis y se reintenta el paso de generación.

#### 1.5 Auditor de Tareas Determinista (`_grade_task_completion`)
Se reemplazó la auditoría 100% LLM por una **lógica determinista por palabras clave** antes de consultar al LLM, reduciendo alucinaciones sobre el uso de herramientas.

### 2. Nueva Arquitectura: Planificación Explícita (Hacia Fase 8)

Para resolver la finalización prematura en tareas multi-acción, se propuso (e inició) la implementación de un **Nodo de Planificación**:
1. **`task_planner`**: Crea un plan de pasos (ej: buscar local -> buscar web -> guardar).
2. **Auditor Consciente**: El auditor compara las herramientas usadas contra el plan generado, no solo contra el mensaje del usuario.

### 3. Estado de los Tests
- **Unit Tests**: 100% PASS (52 tests).
- **Integración**: Estabilizados los tests de enrutamiento multi-turno.
- **RAG**: Links de documentos corregidos para usar `user_id/source` (UUID).
