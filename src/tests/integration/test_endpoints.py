from fastapi.testclient import TestClient
import pytest
import time
import base64
from src.api.main import app
from src.workers.celery_app import celery_app

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

@pytest.mark.integration
def test_ingest_async_flow(client):
    """Verifica que el endpoint /ingest devuelva un task_id y que el status sea rastreable."""
    content = b"Contenido de prueba para ingesta asincrona."
    filename = "async_test.txt"
    
    # 1. POST Ingest
    response = client.post(
        "/api/ingest",
        files={"file": (filename, content, "text/plain")}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "queued"
    assert "task_id" in data
    task_id = data["task_id"]
    
    # 2. GET Status
    # Reintentamos un par de veces si es necesario (asumiendo que el worker está corriendo)
    max_retries = 10
    for i in range(max_retries):
        status_resp = client.get(f"/api/task-status/{task_id}")
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        
        if status_data["status"] == "SUCCESS":
            break
        
        time.sleep(1)
    else:
        pytest.fail("La tarea de ingesta no se completo a tiempo (o el worker no esta activo)")

    assert status_data["status"] == "SUCCESS"
    assert status_data["result"]["status"] == "completed"
