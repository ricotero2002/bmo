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
    # 1. Ingestión
    content = "Este es un documento de prueba técnica para validar el flujo cloud de BMO.".encode("utf-8")
    filename = f"test_cloud_{uuid.uuid4().hex[:8]}.txt"
    
    print(f"\n[+] Iniciando ingesta de {filename}...")
    response = client.post(
        "/api/ingest",
        files={"file": (filename, content, "text/plain")},
        data={"user_id": "test_user_cloud"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "task_id" in data
    task_id = data["task_id"]
    doc_id = data.get("doc_id")
    
    print(f"✅ Ingesta encolada. Task ID: {task_id}")

    # 2. Esperar procesamiento (máximo 60 segundos)
    print("[+] Esperando a que el worker procese el documento...")
    success = False
    for _ in range(12): # 12 * 5s = 60s
        status_resp = client.get(f"/api/task-status/{task_id}")
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        
        if status_data["status"] == "SUCCESS":
            success = True
            break
        elif status_data["status"] == "FAILURE":
            pytest.fail(f"La tarea de Celery falló: {status_data.get('result')}")
            
        time.sleep(5)
    
    if not success:
        pytest.fail("El procesamiento del documento excedió el tiempo límite (60s).")
    
    print("✅ Documento procesado exitosamente.")

    # 3. Query (Búsqueda semántica en Pinecone)
    # Le damos un pequeño margen extra a Pinecone para indexar
    time.sleep(2)
    print("[+] Probando búsqueda semántica (/query)...")
    query_resp = client.post(
        "/api/query",
        json={"query": "prueba técnica", "user_id": "test_user_cloud"}
    )
    assert query_resp.status_code == 200
    query_data = query_resp.json()
    assert "context" in query_data
    # Debería haber encontrado nuestro documento
    assert any("prueba técnica" in ctx for ctx in query_data["context"])
    print("✅ Búsqueda semántica exitosa.")

    # 4. Ask (Conversación con Postgres Checkpointer)
    print("[+] Probando Chat Agent (/ask)...")
    thread_id = str(uuid.uuid4())
    ask_resp = client.post(
        "/api/ask",
        json={
            "message": "¿De qué trata el documento de prueba técnica que subí?",
            "thread_id": thread_id,
            "user_info": {"user_id": "test_user_cloud"}
        }
    )
    assert ask_resp.status_code == 200
    ask_data = ask_resp.json()
    assert "response" in ask_data
    assert len(ask_data["response"]) > 10
    print(f"✅ Respuesta del agente: {ask_data['response'][:50]}...")

    # 5. Listar Chats (Verificar persistencia en Postgres)
    print("[+] Verificando persistencia de chats...")
    list_resp = client.get("/api/chats", params={"user_id": "test_user_cloud"})
    assert list_resp.status_code == 200
    chats = list_resp.json().get("chats", [])
    assert any(c["thread_id"] == thread_id for c in chats)
    print("✅ Chat persistido correctamente.")

    # 6. Cleanup (Eliminar documento)
    if doc_id:
        print(f"[+] Limpiando recursos (doc_id: {doc_id})...")
        del_resp = client.post(
            "/api/delete_file",
            json={"doc_id": doc_id, "user_id": "test_user_cloud"}
        )
        assert del_resp.status_code == 200
        print("✅ Petición de eliminación enviada.")

def test_dead_letter_queue_health(client):
    """Verifica el estado de la DLQ en RabbitMQ."""
    response = client.post("/api/dead-letter-queue-rabbit")
    assert response.status_code == 200
    data = response.json()
    assert "message_count" in data
    assert "status" in data
