import os
from dotenv import load_dotenv

# Cargar variables de entorno antes de importar la app
load_dotenv(override=True)

# Forzar APP_ENV a production para usar los providers cloud (Pinecone, Aiven, OCI)
os.environ["APP_ENV"] = "production"

import pytest
import uuid
import time
import logging
from fastapi.testclient import TestClient
from src.api.main import app
from src.core.config import settings

logger = logging.getLogger(__name__)

# Solo ejecutar si INTEGRATION_ENV=cloud está seteado
pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_ENV") != "cloud",
    reason="Este test suite requiere INTEGRATION_ENV=cloud y credenciales reales de cloud."
)

@pytest.fixture(autouse=True)
def check_cloud_configs():
    """Verifica que las URLs no sean localhost si estamos en modo cloud."""
    if "localhost" in settings.CELERY_BROKER_URL or "127.0.0.1" in settings.CELERY_BROKER_URL:
        pytest.fail(f"❌ Error: CELERY_BROKER_URL apunta a localhost ({settings.CELERY_BROKER_URL}) pero INTEGRATION_ENV=cloud.")
    if "localhost" in settings.REDIS_URL or "127.0.0.1" in settings.REDIS_URL:
        pytest.fail(f"❌ Error: REDIS_URL apunta a localhost ({settings.REDIS_URL}) pero INTEGRATION_ENV=cloud.")

@pytest.fixture
def client():
    """Fixture que provee un TestClient de FastAPI."""
    with TestClient(app) as c:
        yield c

def test_health_endpoint(client):
    """Verifica que el endpoint de salud responda correctamente."""
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_full_workflow_cloud(client):
    """
    Test de flujo completo: Ingestión -> Consulta -> Chat.
    Usa los proveedores reales configurados en APP_ENV=production.
    """
    doc_id = None
    try:
        # 1. Ingestión
        # Añadimos un timestamp al contenido para que el hash sea ÚNICO y no colisione con tareas viejas en Redis/Celery
        unique_id = uuid.uuid4().hex[:8]
        content = f"Este es un documento de prueba técnica ({unique_id}) para validar el flujo cloud de BMO.".encode("utf-8")
        filename = f"test_cloud_{unique_id}.txt"
        user_id = "test_user_cloud"
        
        print(f"\n[+] Iniciando ingesta de {filename} para el usuario {user_id}...")
        response = client.post(
            "/api/ingest",
            files={"file": (filename, content, "text/plain")},
            data={"user_id": user_id}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        task_id = data["task_id"]
        doc_id = data.get("doc_id")
        
        print(f"✅ Ingesta encolada. Task ID: {task_id}")

        # 2. Esperar procesamiento (máximo 60 segundos)
        print("[+] Esperando a que el worker procese el documento en la DB...")
        success = False
        for i in range(40):  
            status_resp = client.get(f"/api/ingestion-status/{doc_id}")
            assert status_resp.status_code == 200
            status_data = status_resp.json()
            
            db_status = status_data.get("status")
            if i % 2 == 0: # Reducimos verbosidad
                print(f"    [Poll {i+1}] Estado actual en DB: {db_status}")
            
            if db_status == "indexed":
                success = True
                break
            elif db_status in ["failed", "dead", "delete_failed"]:
                error_msg = f"El procesamiento falló en DB: {status_data.get('error_msg')}"
                print(f"❌ {error_msg}")
                pytest.fail(error_msg)
                
            time.sleep(3) # Bajamos un poco el delay para ser más rápidos
        
        if not success:
            pytest.fail("El procesamiento del documento excedió el tiempo límite.")
        
        print("✅ Documento procesado exitosamente.")

        # 3. Query (Búsqueda semántica en Pinecone)
        print(f"[+] Probando búsqueda semántica (/query) para '{unique_id}'...")
        found = False
        for i in range(10): # Más reintentos (10 * 3s = 30s)
            time.sleep(3)
            query_resp = client.post(
                "/api/query",
                json={"query": "prueba técnica", "user_id": user_id}
            )
            assert query_resp.status_code == 200
            context = query_resp.json().get("context", [])
            
            if any(unique_id in ctx for ctx in context) or any("prueba técnica" in ctx for ctx in context):
                found = True
                break
            print(f"    [Query Poll {i+1}/10] No encontrado aún...")

        if not found:
            pytest.fail(f"Búsqueda semántica falló: No se recuperó el contexto esperado ({unique_id}).")
        
        print("✅ Búsqueda semántica exitosa.")

        # 4. Ask Stream (Conversación con Postgres Checkpointer)
        print("[+] Probando Chat Agent Stream (/ask/stream)...")
        thread_id = str(uuid.uuid4())
        full_text = ""
        # Usamos client.stream para consumir el SSE correctamente con TestClient
        with client.stream(
            "POST",
            "/api/ask/stream",
            json={
                "message": "¿De qué trata el documento de prueba técnica que subí?",
                "thread_id": thread_id,
                "user_info": {"user_id": user_id},
                "prompt_version": "rag_v3"
            }
        ) as ask_resp:
            assert ask_resp.status_code == 200
            import json
            for line in ask_resp.iter_lines():
                if not line:
                    continue
                # Las líneas de SSE vienen como "data: {...}"
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        if data["type"] == "token":
                            full_text += data["content"]
                        elif data["type"] == "error":
                            pytest.fail(f"Error en stream: {data['content']}")
                    except json.JSONDecodeError:
                        continue
        
        assert len(full_text) > 10
        print(f"✅ Respuesta del agente: {full_text[:50]}...")

        # 5. Listar Chats (Verificar persistencia en Postgres)
        print("[+] Verificando persistencia de chats...")
        # Damos un pequeño tiempo para que BackgroundTask de persistencia termine
        time.sleep(3) 
        
        list_resp = client.get("/api/chats", params={"user_id": user_id})
        assert list_resp.status_code == 200
        chats = list_resp.json().get("chats", [])
        
        # El thread_id debería estar en la lista si la persistencia funcionó
        found_chat = any(c["thread_id"] == thread_id for c in chats)
        if not found_chat:
            print(f"⚠️ Debug: thread_id {thread_id} no encontrado en {chats}")
            
        assert found_chat, f"El thread_id {thread_id} no se persistió en la tabla de chats."
        print("✅ Chat persistido correctamente.")

    finally:
        # 6. Cleanup (Eliminar documento)
        if doc_id:
            print(f"\n[+] Cleanup: Eliminando recursos (doc_id: {doc_id})...")
            # Re-intentamos un par de veces si falla el borrado inicial (por si el worker está ocupado o lock)
            for _ in range(3):
                del_resp = client.post(
                    "/api/delete_file",
                    json={"doc_id": doc_id, "user_id": user_id}
                )
                if del_resp.status_code == 200:
                    print("✅ Petición de eliminación enviada.")
                    break
                time.sleep(2)

def test_dead_letter_queue_health(client):
    """Verifica el estado de la DLQ en RabbitMQ."""
    response = client.post("/api/dead-letter-queue-rabbit")
    assert response.status_code == 200
    data = response.json()
    assert "message_count" in data
    assert "status" in data
