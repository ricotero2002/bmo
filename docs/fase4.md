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
