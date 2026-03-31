import pytest
from fastapi.testclient import TestClient
from src.api.main import app
from unittest.mock import MagicMock
from src.api.dependencies import get_chat_provider
import uuid

client = TestClient(app)

def test_get_chats_success():
    mock_provider = MagicMock()
    mock_provider.get_user_chats.return_value = [
        {"thread_id": str(uuid.uuid4()), "title": "Test", "created_at": "2024-01-01"}
    ]
    app.dependency_overrides[get_chat_provider] = lambda: mock_provider

    response = client.get("/api/chats?user_id=123")
    assert response.status_code == 200
    assert len(response.json()["chats"]) == 1

def test_get_messages_success():
    mock_provider = MagicMock()
    mock_provider.get_chat_messages.return_value = [
        {"id": str(uuid.uuid4()), "role": "user", "content": "Hi", "created_at": "2024-01-01"}
    ]
    app.dependency_overrides[get_chat_provider] = lambda: mock_provider

    thread_id = str(uuid.uuid4())
    response = client.get(f"/api/chats/{thread_id}/messages")
    assert response.status_code == 200
    assert len(response.json()["messages"]) == 1

def test_get_messages_invalid_uuid():
    response = client.get(f"/api/chats/invalid-uuid/messages")
    assert response.status_code == 400
    
# Se limpia el override para no afectar a otros tests en el entorno
app.dependency_overrides.clear()

def test_ask_empty_thread_id():
    # Test que al usar POST /ask sin thread_id, devuelva uno generado.
    from src.api.dependencies import get_agent_service
    
    class MockAgentService:
        async def chat(self, message, thread_id, user_info, prompt_version):
            # Simulamos el retorno del LangGraph
            class MockMessage:
                def __init__(self, content):
                    self.content = content
            return {"generated": MockMessage("Mocked response"), "messages": []}
            
    app.dependency_overrides[get_agent_service] = lambda: MockAgentService()
    
    response = client.post("/api/ask", json={
        "message": "Hola sin thread ID",
        "user_info": {"user_id": "test"}
    })
    
    assert response.status_code == 200
    data = response.json()
    assert "response" in data
    assert "thread_id" in data
    assert data["thread_id"] is not None
    assert len(data["thread_id"]) > 10 # Es un UUID

    app.dependency_overrides.clear()
