from airflow.decorators import dag, task
from airflow.operators.empty import EmptyOperator
from datetime import datetime, timedelta
import os
import requests
import json
import hashlib
import uuid
import logging
from notion_client import Client
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Intentar encontrar la raíz del proyecto para src.providers
import sys
possible_roots = [
    os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')), # Local
    '/opt/project' # Docker Airflow
]
for root in possible_roots:
    if os.path.exists(os.path.join(root, 'src')):
        if root not in sys.path:
            sys.path.append(root)
        break

# Forzar el uso del provider OCI si no se define
os.environ.setdefault("APP_ENV", "production") 

API_URL = os.getenv("BMO_API_URL", "http://host.docker.internal:8000")

default_args = {
    'owner': 'bmo_airflow',
    'depends_on_past': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=2),
}

@dag(
    dag_id='production_notion_cdc_sync',
    default_args=default_args,
    schedule_interval='@daily',
    start_date=datetime(2026, 4, 1),
    catchup=False,
    tags=['ingestion', 'notion', 'cdc'],
)
def notion_sync_pipeline():

    start = EmptyOperator(task_id="start")
    end = EmptyOperator(task_id="end")

    @task
    def get_users_to_sync():
        """Consulta al backend qué usuarios necesitan sincronización de Notion."""
        response = requests.get(f"{API_URL}/api/internal/sync/notion/targets")
        response.raise_for_status()
        return response.json()

    @task
    def sync_notion_user(target: dict):
        """Procesa un usuario, maneja paginación, MinIO batching y state update."""
        user_id = target["user_id"]
        notion = Client(auth=target["access_token"])
        last_sync = target.get("last_sync_at")
        batch_id = str(uuid.uuid4())
        
        database_id = target["source_id"]
        query_payload = {}
        
        if last_sync:
            logger.info(f"🔄 CDC para {user_id} desde {last_sync}")
            query_payload["filter"] = {
                "timestamp": "last_edited_time",
                "last_edited_time": {"on_or_after": last_sync}
            }
        else:
            logger.info(f"🚀 FULL LOAD para {user_id}")

        has_more = True
        next_cursor = None
        files_to_trigger = []
        
        # Conectar a MinIO/OCI (StorageProvider)
        from src.providers.storage.factory import StorageFactory
        storage = StorageFactory.get_storage()

        # PAGINACIÓN: Traemos de a 100 y subimos para no explotar la RAM
        while has_more:
            if next_cursor:
                query_payload["start_cursor"] = next_cursor
                
            # Usamos el método estándar del SDK (asegurando versión 2.2.1)
            response = notion.databases.query(database_id=database_id, **query_payload)
            results = response.get("results", [])

            for page in results:

                # 1. Empaquetar y Hashear
                content_bytes = json.dumps(page).encode('utf-8')
                file_hash = hashlib.sha256(content_bytes).hexdigest()
                
                # 2. Guardar en Storage
                object_name = f"bronze/notion/{user_id}/{batch_id}/{page['id']}.json"
                storage.upload_file(file_data=content_bytes, object_name=object_name)
                
                files_to_trigger.append({
                    "object_name": object_name,
                    "file_hash": file_hash,
                    "metadata": {"note_id": page["id"]}
                })
            
            has_more = response.get("has_more")
            next_cursor = response.get("next_cursor")

        # 3. Mandar los triggers al backend si hubo cambios
        if files_to_trigger:
            payload = {
                "user_id": user_id,
                "source_type": "notion",
                "files": files_to_trigger
            }
            res = requests.post(f"{API_URL}/api/ingest/trigger", json=payload)
            res.raise_for_status()
            
            # 4. Avisar al backend que actualice el last_sync_at en la DB
            res = requests.post(f"{API_URL}/api/internal/sync/notion/update_state", json={
                "user_id": user_id,
                "status": "success",
                "last_sync_at": datetime.utcnow().isoformat()
            })
            res.raise_for_status()
            
        return f"User {user_id} sync complete. Files: {len(files_to_trigger)}"

    # Dinámica de Tareas (Dynamic Task Mapping)
    # Crea una tarea paralela independiente por cada usuario devuelto por la API
    targets = get_users_to_sync()
    sync_tasks = sync_notion_user.expand(target=targets)

    # Orden de ejecución
    start >> targets
    sync_tasks >> end

# Instanciar el DAG
dag = notion_sync_pipeline()
