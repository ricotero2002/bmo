# Fase 4: Orquestación Agéntica, Persistencia y Evaluación Estricta

Esta fase se centró en preparar la aplicación para producción integrando servicios de nube (AWS), robusteciendo el razonamiento del agente, implementando transaccionalidad distribuida para el borrado de datos y estableciendo un pipeline de pruebas deterministas y evaluativas.

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
Cada chunk indexado tiene metadatos esenciales para el **Hybrid Search**:
```json
{
  "source": "informe.pdf",
  "file_hash": "abc123...",
  "created_at": 1774129256.646043,
  "page_number": 2,
  "chunk_index": 4,
  "user_id": "user_123"
}
```

### `source_id_key` y actualizaciones
El `SQLRecordManager` usa `source_id_key="source"`. Esto significa:
- **Archivo idéntico** → `file_hash` lo detecta → skip total
- **Archivo modificado** → el `RecordManager` elimina los chunks viejos del `source` y agrega los nuevos (`cleanup="incremental"`)

---

## 2. Alembic — Migraciones de Base de Datos

Se implementó Alembic para gestionar la evolución del esquema relacional (PostgreSQL / RDS).

**Comandos principales implementados:**
```bash
alembic upgrade head # Aplica migraciones
alembic revision --autogenerate -m "descripcion del cambio" # Crea migraciones
```
*Las mismas variables de entorno se reutilizan tanto para local como Producción.*

---

## 3. Providers de Producción AWS

La aplicación soporta la abstracción hacia la nube mediante el patrón Provider:

| Provider | Local | Producción (AWS) | Free Tier |
|---|---|---|---|
| **Vector Store** | ChromaDB (Docker) | OpenSearch | ⚠️ No free tier |
| **Storage** | MinIO (Docker) | **S3** | ✅ 5GB + 20K GETs |
| **Cache** | Redis (Docker) | **DynamoDB** | ✅ 25GB + 200M requests |
| **PostgreSQL** | PostgreSQL local | **RDS PostgreSQL** | ✅ Compartido |

---

## 4. Evolución del Agente: Seguridad, Metadatos y Control de Errores

A lo largo de la Fase 4, se consolidó la arquitectura del agente para hacerla robusta, segura y contextualmente consciente.

### Retriever Unificado y Seguridad (RunnableConfig)
Existe un **único retriever unificado** (`knowledge_base_retriever`). 
Para evitar que el LLM tenga control sobre la segmentación de datos por usuario, se implementó la inyección del `user_id` a través de `RunnableConfig`. El LLM desconoce este parámetro y por lo tanto no puede manipularlo maliciosamente.

### Inyección de Tiempo y Filtrado de Fechas Retrocompatible
El modelo recibe `{{ today }}` en formato ISO `YYYY-MM-DD`. Cuando el usuario hace consultas temporales, el agente deduce un límite y lo pasa como `date_from`.
La tool unificada usa una condición lógica `$or` para buscar tanto por `Unix Timestamp` (formato Float nuevo) como por `ISO String` (formato viejo), asegurando retrocompatibilidad total con documentos ingeridos previamente sin necesidad de re-indexar.

### Control de Errores y Retries Agotados vía `Command`
- **Guardia Previa:** Si la tool falla, devuelve un string con el prefijo `ERROR_TOOL:`.
- **Reintento Inmediato (`Command`):** El nodo de evaluación (`_grade_documents`) detecta ese prefijo e interrumpe el flujo enviando un `Command(goto='agent')`.
- **Manejo de Respuestas Fallidas:** Si las búsquedas legítimas agotan los `MAX_RETRIES`, un `Command` emite una orden explícita al LLM para que le pida más contexto al usuario (evitando que omita el problema).

---

## 5. Streaming de Respuestas (SSE) y CORS

Para una interfaz fluida (tipo ChatGPT), la API expone el texto en tiempo real.
- Se implementó un nuevo endpoint `/api/ask/stream` que utiliza **Server-Sent Events (SSE)** vía `astream_events` de Langchain (versión `v2`).
- El frontend recibe dos clases de eventos:
  - `type: status` (visibilidad interna de lo que "piensa" el agente, ej: "Buscando en la BD...").
  - `type: token` (texto puro de la respuesta generada).
- Se agregó el `CORSMiddleware` a la aplicación FastAPI para permitir integraciones frontend locales libres de fricción.

---

## 6. Transaccionalidad Distribuida (Borrado Lógico)

Dado que es imposible usar transacciones SQL convencionales entre PostgreSQL, ChromaDB/OpenSearch y MinIO/S3, se implementó un **Saga Pattern simplificado**.
La tarea Celery `delete_document_task` maneja la idempotencia ejecutando las eliminaciones en este orden crítico:
1. **Vector Store:** Aisla los chunks en `RecordManager` para evitar fuga de datos primero.
2. **Object Storage (MinIO/S3):** Borra el archivo físico.
3. **Hard Delete (SQL):** Se limpia el job status de la base.

Se agregaron Unit Tests completos que simulan caídas de red o fallos a mitad de proceso asegurando la reconexión y que la idempotencia nunca falle un `assert`.

---

## 7. Evaluación de Calidad (LLMOps) y Spy Tests

Se configuró un entorno de evaluación estricto en el pipeline CI/CD sin necesidad de levantar contenedores.

### Test de "Inteligencia" en el Tool Calling (Spy Pattern)
Se agregó `test_agent_tools.py` que inyecta una herramienta "Spy" que reemplaza la llamada a DB. Esto valida **en apenas 7 segundos** que el LLM armó correctamente el `query`, extrajo adecuadamente el intento de la pregunta y filtró limpiamente por el `user_id` en el objeto de configuración, sin depender de la base de datos real.

### Evaluación Continua (DeepEval)
En `test_agent_evaluation.py`, implementamos Gemini como "LLM as a Judge" con dos métricas críticas antes del merge:
- **Faithfulness (Fidelidad):** Mide que la IA no alucine inventando datos que no están en el contexto ficticio enviado (Umbral: >0.85).
- **Answer Relevancy:** Mide la precisión de la respuesta de acuerdo a la pregunta solicitada (Umbral: >0.80).
- Se diseñó un test interno del tipo **A/B Testing** para el Prompting: si `rag_v2` obtiene menos puntaje en estas métricas que un baseline (`rag_v1`), el test en GitHub Actions rechaza el cambio al PR.
