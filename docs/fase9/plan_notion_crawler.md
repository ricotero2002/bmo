# Plan de Implementación: Notion CDC Crawler Completo

**Estado actual:** El DAG `production_notion_cdc_sync` sincroniza un único `database_id` por usuario.  
**Objetivo:** Convertirlo en un crawler recursivo (BFS) que descubra y sincronice todo el árbol de contenido autorizado, con CDC granular por página y detección de páginas eliminadas.

---

## Diagnóstico del Estado Actual

| Componente | Estado | Limitación |
|---|---|---|
| `UserIntegration` | ✅ Implementado | Solo guarda un `source_id` (1 DB) |
| `IngestionSyncState` | ✅ Implementado | Solo rastrea "última vez que se sincronizó Notion" a nivel usuario |
| `notion_sync.py` DAG | ⚠️ Parcial | Solo descarga el JSON crudo de 1 BD, no hace BFS, no detecta borrados |
| Detección de borrados | ❌ No existe | Sin `NotionSyncMetadata` no hay forma de comparar |
| Crawler recursivo | ❌ No existe | No recorre sub-páginas ni sub-bases de datos |
| Contenido en Markdown | ❌ No existe | Sube JSON crudo, no Markdown limpio |

---

## Fase 1 — Modelo de Datos (`models.py` + Alembic)

### 1.1 Nueva tabla: `NotionSyncMetadata`

Rastrea el estado individual de cada página/bloque descubierto. Es la "memoria" del crawler.

```python
class NotionSyncMetadata(Base):
    __tablename__ = "notion_sync_metadata"

    id               = Column(GUID, primary_key=True, default=uuid.uuid4)
    user_id          = Column(String(255), nullable=False, index=True)
    notion_id        = Column(String(255), nullable=False, index=True) # ID de Notion
    parent_id        = Column(String(255), nullable=True)              # Padre en el árbol
    object_type      = Column(String(50), nullable=False)              # 'page' | 'database'
    last_edited_time = Column(DateTime, nullable=True)                 # Extraído de la API
    file_hash        = Column(String(256), nullable=True)              # Hash de contenido
    is_archived      = Column(Integer, default=0)                      # 1=borrado (Oracle compat)
    created_at       = Column(DateTime, default=datetime.utcnow)
    updated_at       = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

> **Nota Oracle:** Usar `Integer` en lugar de `Boolean` para evitar `ORA-00906`. `1=archivado`, `0=activo`.

### 1.2 Cambio semántico en `UserIntegration.source_id`

No cambia el schema. Si `source_id == "workspace"`, el backend usa `notion.search()` para descubrir todas las bases de datos autorizadas. Si es un UUID, arranca desde ese nodo raíz.

### 1.3 Nuevos métodos en `StatusProvider`

```python
def upsert_notion_page_metadata(user_id, notion_id, parent_id, object_type, last_edited_time, file_hash, is_archived)
def get_notion_page_metadata(user_id, notion_id) -> Optional[dict]
def get_all_notion_page_ids_for_user(user_id) -> List[str]  # Para orphan detection
def mark_notion_pages_archived(user_id, notion_ids: List[str])
```

### 1.4 Migración Alembic

```bash
alembic revision --autogenerate -m "fase 9 notion sync metadata tabla"
alembic upgrade head
```

---

## Fase 2 — Nuevo DAG: Crawler BFS

### 2.1 Arquitectura del DAG

```
start
  └── get_root_targets_per_user    # Dynamic Task Mapping por usuario
        └── crawl_notion_tree      # BFS: descubre todo el árbol
              └── detect_orphans   # Compara visitados vs. almacenados
                    └── end
```

### 2.2 Tarea `get_root_targets_per_user`

- Llama a `GET /api/internal/sync/notion/targets`.
- Si `source_id == "workspace"`, usa `notion.search(filter={"value": "database"})` para auto-descubrir.
- Retorna lista de `{ user_id, access_token, root_ids: [list] }`.

### 2.3 Tarea `crawl_notion_tree` (algoritmo BFS)

```
cola = [ raiz_id_1, raiz_id_2, ... ]
visitados = set()

while cola no vacía:
    node_id = cola.pop()
    visitados.add(node_id)

    node_info = check_node_status(notion, node_id)

    if node_info es None o in_trash:
        continue  # Nodo inaccesible → orphan detection lo capturará

    saved_meta = status_provider.get_notion_page_metadata(user_id, node_id)
    contenido_cambio = (
        saved_meta is None or
        saved_meta["last_edited_time"] < parse(node_info["last_edited_time"])
    )

    if contenido_cambio and node_info["type"] == "page":
        markdown = get_page_markdown(notion, node_id)
        upload_to_storage(markdown, user_id, node_id)
        trigger_ingestion(user_id, node_id)

    upsert_page_state(user_id, node_id, node_info)

    # Continuar BFS
    if node_info["type"] == "database":
        pages = query_database(notion, node_id)
        cola.extend([p["id"] for p in pages])
    elif node_info["type"] == "page":
        children = find_children_nodes(notion, node_id)  # child_page + child_database
        cola.extend([c["id"] for c in children])
```

### 2.4 Tarea `detect_orphans`

Solo se ejecuta si el crawl completó sin error (se pasa flag de éxito).

```python
all_saved = status_provider.get_all_notion_page_ids_for_user(user_id)
orphans = [n_id for n_id in all_saved if n_id not in visitados]
if orphans:
    status_provider.mark_notion_pages_archived(user_id, orphans)
    trigger_delete(user_id, orphans)  # POST al backend para eliminar vectores
```

---

## Fase 3 — Descarga como Markdown (reemplaza JSON crudo)

### 3.1 Función `get_page_markdown`

```python
def get_page_markdown(notion: Client, page_id: str) -> str:
    try:
        response = notion.request(
            path=f"pages/{page_id}/markdown",
            method="GET"
        )
        return response.get("markdown", "")
    except Exception:
        # Fallback: construir desde bloques
        return build_markdown_from_blocks(notion, page_id)
```

### 3.2 Nueva ruta en Storage

```
bronze/notion/{user_id}/{page_id}.md   ← limpio, listo para chunking
```

El worker de Celery ya no necesita parsear JSON complejo de Notion.

---

## Fase 4 — Nuevos Endpoints FastAPI

| Endpoint | Método | Propósito |
|---|---|---|
| `/api/internal/sync/notion/targets` | `GET` | Existente. Sin cambios. |
| `/api/internal/sync/notion/update_state` | `POST` | Existente. Sin cambios. |
| `/api/internal/sync/notion/upsert_page` | `POST` | **NUEVO.** Airflow reporta metadatos de cada página. |
| `/api/internal/sync/notion/archive_pages` | `POST` | **NUEVO.** Airflow notifica páginas huérfanas para archivarlas. |

---

## Fase 5 — Seguridad de los Endpoints Internos

> Pendiente del `fase9.md`: *"Falta hacer seguros los endpoints que se llaman desde Airflow."*

**Estrategia: API Key compartida (secreto de Airflow).**

1. Definir `AIRFLOW_INTERNAL_API_KEY` en `.env` y como variable de Airflow.
2. Airflow incluye header `X-Internal-Key: {key}` en cada petición a `/api/internal/`.
3. FastAPI valida con `Depends(verify_internal_key)`:

```python
INTERNAL_KEY = os.getenv("AIRFLOW_INTERNAL_API_KEY")

def verify_internal_key(x_internal_key: str = Header(...)):
    if x_internal_key != INTERNAL_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")
```

---

## Secuencia de Implementación

| Semana | Tarea | Archivos modificados |
|---|---|---|
| **1** | `NotionSyncMetadata` en `models.py` + Alembic migration | `models.py`, `alembic/versions/` |
| **1** | Nuevos métodos en `StatusProvider` | `status_provider.py` |
| **2** | Endpoints `/upsert_page` y `/archive_pages` | `integrations.py` |
| **2** | `verify_internal_key` en todos los `/internal/` | `dependencies.py`, `integrations.py` |
| **3** | Reemplazar `notion_sync.py` con crawler BFS completo | `dags/notion_sync.py` |
| **3** | Prueba E2E: Full Load → CDC → Orphan detection | Manual |

---

## Riesgos y Mitigaciones

| Riesgo | Mitigación |
|---|---|
| Rate Limiting de Notion (3 req/s por token) | `time.sleep(0.35)` entre llamadas en el BFS |
| Árbol muy profundo (>10k páginas en RAM) | Si supera un umbral, persistir la cola BFS en Redis o en la DB auxiliar |
| Endpoint `/markdown` no disponible | Fallback implementado con `blocks.children.list` + reconstrucción manual |
| Oracle no soporta `Boolean` | Usar `Integer` (0/1) mapeado como `is_archived` |
| Orphan false-positive por crash | Orphan detection solo se ejecuta si el crawl completo fue exitoso |
