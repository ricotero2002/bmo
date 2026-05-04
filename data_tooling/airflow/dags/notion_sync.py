from airflow.decorators import dag, task
from airflow.operators.empty import EmptyOperator
from datetime import datetime, timedelta, timezone
import os
import time
import hashlib
import requests
import json
import uuid
import logging
from notion_client import Client
from dateutil.parser import parse as parse_dt
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# --- Path setup para importar src.providers ---
import sys
possible_roots = [
    os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')),  # Local
    '/opt/project',  # Docker Airflow
]
for root in possible_roots:
    if os.path.exists(os.path.join(root, 'src')):
        if root not in sys.path:
            sys.path.append(root)
        break

os.environ.setdefault("APP_ENV", "production")

API_URL = os.getenv("BMO_API_URL", "http://host.docker.internal:8000")
INTERNAL_API_KEY = os.getenv("AIRFLOW_INTERNAL_API_KEY", "")
NOTION_RATE_LIMIT_SLEEP = 0.35  # 3 req/s max según la API de Notion

# Headers para los endpoints internos del backend
def _internal_headers():
    return {"X-Internal-Key": INTERNAL_API_KEY, "Content-Type": "application/json"}

default_args = {
    'owner': 'bmo_airflow',
    'depends_on_past': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
}


# ─────────────────────────────────────────────
# Funciones del crawler (helpers reutilizables)
# ─────────────────────────────────────────────

def check_node_status(notion: Client, node_id: str, node_type: str) -> dict | None:
    """Obtiene los metadatos de un nodo (última edición, si está en papelera)."""
    try:
        time.sleep(NOTION_RATE_LIMIT_SLEEP)
        if node_type == "database":
            data = notion.databases.retrieve(database_id=node_id)
        else:
            data = notion.pages.retrieve(page_id=node_id)

        return {
            "id": data["id"].replace("-", ""),
            "type": node_type,
            "last_edited_time": data.get("last_edited_time"),
            "in_trash": data.get("in_trash", False) or data.get("archived", False),
        }
    except Exception as e:
        logger.warning(f"Nodo {node_id} inaccesible (quizás borrado o sin permisos): {e}")
        return None


def query_database_pages(notion: Client, database_id: str) -> list:
    """Obtiene todas las páginas (hijos) de una database de Notion con paginación completa."""
    pages = []
    has_more = True
    next_cursor = None

    while has_more:
        time.sleep(NOTION_RATE_LIMIT_SLEEP)
        payload = {}
        if next_cursor:
            payload["start_cursor"] = next_cursor

        response = notion.databases.query(database_id=database_id, **payload)
        pages.extend(response.get("results", []))
        has_more = response.get("has_more", False)
        next_cursor = response.get("next_cursor")

    return pages


def find_children_nodes(notion: Client, block_id: str) -> list:
    """Busca sub-páginas y sub-databases dentro de una página (para BFS recursivo)."""
    children = []
    has_more = True
    next_cursor = None

    while has_more:
        time.sleep(NOTION_RATE_LIMIT_SLEEP)
        response = notion.blocks.children.list(
            block_id=block_id,
            start_cursor=next_cursor,
            page_size=100,
        )

        for block in response.get("results", []):
            if block["type"] == "child_page":
                children.append({"type": "page", "id": block["id"].replace("-", "")})
            elif block["type"] == "child_database":
                children.append({"type": "database", "id": block["id"].replace("-", "")})

        has_more = response.get("has_more", False)
        next_cursor = response.get("next_cursor")

    return children


def get_page_markdown(notion: Client, page_id: str) -> str:
    """
    Descarga el contenido de una página como Markdown limpio.
    Usa el endpoint nativo si está disponible; sino construye desde bloques.
    """
    try:
        time.sleep(NOTION_RATE_LIMIT_SLEEP)
        response = notion.request(path=f"pages/{page_id}/markdown", method="GET")
        return response.get("markdown", "")
    except Exception:
        # Fallback: reconstruir markdown desde los bloques de texto
        return _build_markdown_from_blocks(notion, page_id)


def _build_markdown_from_blocks(notion: Client, block_id: str, depth: int = 0) -> str:
    """Fallback: construye Markdown iterando los bloques hijos de una página."""
    lines = []
    has_more = True
    next_cursor = None

    while has_more:
        time.sleep(NOTION_RATE_LIMIT_SLEEP)
        response = notion.blocks.children.list(block_id=block_id, start_cursor=next_cursor, page_size=100)

        for block in response.get("results", []):
            b_type = block.get("type")
            b_data = block.get(b_type, {})
            rich_text = b_data.get("rich_text", [])
            text = "".join(t.get("plain_text", "") for t in rich_text)
            indent = "  " * depth

            if b_type == "paragraph":
                lines.append(f"{indent}{text}")
            elif b_type in ("heading_1", "heading_2", "heading_3"):
                level = int(b_type[-1])
                lines.append(f"\n{'#' * level} {text}\n")
            elif b_type == "bulleted_list_item":
                lines.append(f"{indent}- {text}")
            elif b_type == "numbered_list_item":
                lines.append(f"{indent}1. {text}")
            elif b_type == "to_do":
                checked = "x" if b_data.get("checked") else " "
                lines.append(f"{indent}- [{checked}] {text}")
            elif b_type == "code":
                lang = b_data.get("language", "")
                lines.append(f"\n```{lang}\n{text}\n```\n")
            elif b_type == "quote":
                lines.append(f"{indent}> {text}")

            # Recursivo para bloques con hijos
            if block.get("has_children"):
                child_md = _build_markdown_from_blocks(notion, block["id"], depth + 1)
                lines.append(child_md)

        has_more = response.get("has_more", False)
        next_cursor = response.get("next_cursor")

    return "\n".join(lines)


# ─────────────────────────────────────────────
# DAG
# ─────────────────────────────────────────────

@dag(
    dag_id='production_notion_cdc_sync',
    default_args=default_args,
    schedule_interval='@daily',
    start_date=datetime(2026, 4, 1),
    catchup=False,
    tags=['ingestion', 'notion', 'cdc', 'bfs'],
)
def notion_sync_pipeline():

    start = EmptyOperator(task_id="start")
    end = EmptyOperator(task_id="end")

    @task
    def get_users_to_sync() -> list:
        """Consulta al backend qué usuarios tienen integraciones de Notion activas."""
        response = requests.get(
            f"{API_URL}/api/internal/sync/notion/targets",
            headers=_internal_headers(),
        )
        response.raise_for_status()
        return response.json()

    @task
    def crawl_notion_tree(target: dict) -> dict:
        """
        Crawler BFS que recorre todo el árbol de contenido de Notion para un usuario.
        Detecta contenido nuevo/modificado y lo descarga como Markdown a OCI/MinIO.
        Devuelve el set de IDs visitados para la tarea de orphan detection.
        """
        from src.providers.storage.factory import StorageFactory

        user_id = target["user_id"]
        access_token = target["access_token"]
        source_id = target["source_id"]

        notion = Client(auth=access_token)
        storage = StorageFactory.get_storage()

        # Determinar nodos raíz
        if source_id == "workspace":
            logger.info(f"🌐 Descubriendo todo el contenido del workspace para {user_id}")
            root_queue = []
            has_more = True
            next_cursor = None
            
            # Buscamos todo sin filtro exclusivo, paginando por si hay más de 100 raíces compartidas
            while has_more:
                time.sleep(NOTION_RATE_LIMIT_SLEEP)
                payload = {"page_size": 100}
                if next_cursor:
                    payload["start_cursor"] = next_cursor
                    
                search_response = notion.search(**payload)
                
                for item in search_response.get("results", []):
                    obj_type = item.get("object") # Puede ser 'page' o 'database'
                    if obj_type in ["page", "database"]:
                        root_queue.append({
                            "type": obj_type, 
                            "id": item["id"].replace("-", "")
                        })
                
                has_more = search_response.get("has_more", False)
                next_cursor = search_response.get("next_cursor")
        else:
            # Si no es workspace, es un ID específico. Probamos qué es.
            raw_id = source_id.replace("-", "")
            try:
                notion.databases.retrieve(database_id=raw_id)
                root_queue = [{"type": "database", "id": raw_id}]
            except Exception:
                # Si falla, asumimos que es página (el crawler lo validará luego con check_node_status)
                root_queue = [{"type": "page", "id": raw_id}]

        queue = list(root_queue)
        visited = set()
        files_to_trigger = []
        pending_metadata_updates = []
        
        logger.info(f"🚀 Iniciando BFS para {user_id} | Raíces: {len(queue)}")

        try:
            while queue:
                node = queue.pop(0)
                node_id = node["id"]
                node_type = node["type"]

                if node_id in visited:
                    continue

                # 1. Obtener metadatos del nodo
                node_info = check_node_status(notion, node_id, node_type)
                if node_info is None or node_info.get("in_trash"):
                    logger.info(f"⛔ Nodo {node_id} inaccesible o en papelera — ignorado")
                    continue

                visited.add(node_id)
                last_edited_str = node_info.get("last_edited_time")
                last_edited_dt = parse_dt(last_edited_str) if last_edited_str else None
                
                # Aseguramos que la fecha de Notion tenga zona horaria UTC
                if last_edited_dt and last_edited_dt.tzinfo is None:
                    last_edited_dt = last_edited_dt.replace(tzinfo=timezone.utc)

                # 2. CDC: ¿Cambió desde la última vez?
                saved_meta_response = requests.get(
                    f"{API_URL}/api/internal/sync/notion/page_meta/{user_id}/{node_id}",
                    headers=_internal_headers(),
                )
                
                saved_last_edited = None
                if saved_meta_response.status_code == 200:
                    saved = saved_meta_response.json()
                    if saved.get("last_edited_time"):
                        saved_last_edited = parse_dt(saved["last_edited_time"])
                        # Aseguramos que la fecha de la base de datos tenga zona horaria UTC
                        if saved_last_edited.tzinfo is None:
                            saved_last_edited = saved_last_edited.replace(tzinfo=timezone.utc)

                content_changed = (
                    saved_last_edited is None or
                    (last_edited_dt is not None and last_edited_dt > saved_last_edited)
                )

                # 3. Si es página y cambió, descargar Markdown
                if node_type == "page" and content_changed:
                    logger.info(f"📄 Descargando página {node_id} para {user_id}")
                    markdown_content = get_page_markdown(notion, node_id)
                    content_bytes = markdown_content.encode("utf-8")
                    file_hash = hashlib.sha256(content_bytes).hexdigest()
                    object_name = f"bronze/notion/{user_id}/{node_id}.md"

                    storage.upload_file(file_data=content_bytes, object_name=object_name)

                    files_to_trigger.append({
                        "object_name": object_name,
                        "filename": f"{node_id}.md",
                        "file_hash": file_hash,
                        "metadata": {"notion_id": node_id, "object_type": "page"},
                    })

                    pending_metadata_updates.append({
                        "notion_id": node_id,
                        "parent_id": node.get("parent_id"),
                        "object_type": "page",
                        "last_edited_time": last_edited_str or datetime.utcnow().isoformat(),
                        "file_hash": file_hash,
                        "is_archived": 0,
                    })

                elif node_type == "database":
                    # Reportar la database en el mapa de metadatos (sin descargar contenido)
                    pending_metadata_updates.append({
                        "notion_id": node_id,
                        "parent_id": node.get("parent_id"),
                        "object_type": "database",
                        "last_edited_time": last_edited_str or datetime.utcnow().isoformat(),
                        "is_archived": 0,
                    })

                # 4. Continuar BFS: agregar hijos a la cola
                if node_type == "database":
                    pages = query_database_pages(notion, node_id)
                    for page in pages:
                        page_id = page["id"].replace("-", "")
                        if page_id not in visited:
                            queue.append({"type": "page", "id": page_id, "parent_id": node_id})

                elif node_type == "page":
                    children = find_children_nodes(notion, node_id)
                    for child in children:
                        if child["id"] not in visited:
                            child["parent_id"] = node_id
                            queue.append(child)

            logger.info(f"✅ BFS completado para {user_id}. Nodos visitados: {len(visited)}")

            # 5. Disparar ingesta de los archivos nuevos/modificados
            if files_to_trigger:
                logger.info(f"📤 Disparando ingesta para {len(files_to_trigger)} archivos...")
                requests.post(
                    f"{API_URL}/api/ingest/trigger",
                    json={"user_id": user_id, "source_type": "notion", "files": files_to_trigger},
                    headers=_internal_headers(),
                ).raise_for_status()

            # 6. Actualizar el estado y metadatos (en lote)
            requests.post(
                f"{API_URL}/api/internal/sync/notion/update_state",
                json={
                    "user_id": user_id,
                    "status": "success",
                    "last_sync_at": datetime.utcnow().isoformat(),
                },
                headers=_internal_headers(),
            ).raise_for_status()

            if pending_metadata_updates:
                logger.info(f"💾 Guardando metadatos de {len(pending_metadata_updates)} nodos...")
                requests.post(
                    f"{API_URL}/api/internal/sync/notion/batch_upsert",
                    json={"user_id": user_id, "updates": pending_metadata_updates},
                    headers=_internal_headers(),
                ).raise_for_status()

        except Exception as e:
            logger.error(f"❌ Error crítico en el crawling de {user_id}: {e}")
            raise e

        return {"user_id": user_id, "visited_ids": list(visited), "files_synced": len(files_to_trigger)}

    @task
    def detect_orphans(crawl_result: dict):
        """
        Detecta páginas que estaban en la DB pero no fueron visitadas en el BFS.
        Solo corre si el crawl completó sin errores (garantizado por el Depends de Airflow).
        """
        user_id = crawl_result["user_id"]
        visited_ids = set(crawl_result["visited_ids"])

        # Obtener todos los IDs que teníamos guardados para este usuario
        response = requests.get(
            f"{API_URL}/api/internal/sync/notion/all_page_ids/{user_id}",
            headers=_internal_headers(),
        )
        response.raise_for_status()
        all_saved_ids = response.json().get("notion_ids", [])

        orphans = [n_id for n_id in all_saved_ids if n_id not in visited_ids]

        if orphans:
            logger.warning(f"🗑️ Huérfanos detectados para {user_id}: {len(orphans)} páginas")
            requests.post(
                f"{API_URL}/api/internal/sync/notion/archive_pages",
                json={"user_id": user_id, "notion_ids": orphans},
                headers=_internal_headers(),
            ).raise_for_status()
        else:
            logger.info(f"✨ No hay huérfanos para {user_id}")

    # --- Flujo del DAG ---
    targets = get_users_to_sync()
    crawl_results = crawl_notion_tree.expand(target=targets)
    orphan_tasks = detect_orphans.expand(crawl_result=crawl_results)

    start >> targets
    orphan_tasks >> end


dag = notion_sync_pipeline()
