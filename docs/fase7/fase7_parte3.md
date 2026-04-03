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

- [ ] **Detección dinámica de idioma/región en `web_search.py`**: Actualmente `region="es-es"` está hardcodeado. La idea es detectar el idioma del mensaje del usuario (ej. usando `langdetect`) y mapear al código de región correcto de DuckDuckGo. Idealmente configurable por perfil de usuario (campo a agregar al crear la cuenta).

- [ ] **Frontend — Renderizar `### Fuentes` como links clickeables**: Cuando el frontend (Next.js) reciba el Markdown de BMO, librerías como `react-markdown` renderizan automáticamente los `[texto](url)` como tags `<a>`. Las Presigned URLs de OCI/MinIO se abren directamente en el navegador. Esto no requiere cambios de backend.
