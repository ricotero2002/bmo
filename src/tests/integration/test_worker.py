import pytest
import time
from src.workers.tasks import process_document_task
from celery.result import AsyncResult
from src.workers.celery_app import celery_app

@pytest.mark.integration
def test_worker_connectivity():
    """Verifica que el worker pueda recibir y procesar una tarea simple."""
    # Nota: Este test requiere que RabbitMQ y Redis estén corriendo
    # o que se use un mock de Celery. Para integración real, asumimos infra disponible.
    
    test_text = "Contenido de prueba para el worker"
    test_filename = "test_connectivity.txt"
    
    # 1. Enviar tarea
    import base64
    content_b64 = base64.b64encode(test_text.encode()).decode()
    
    task = process_document_task.delay(content_b64, test_filename)
    assert task.id is not None
    
    # 2. Esperar resultado (con timeout)
    result = task.get(timeout=10)
    
    assert result["status"] == "completed"
    assert result["filename"] == test_filename
    assert "chunks_created" in result
