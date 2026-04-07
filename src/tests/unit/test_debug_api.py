import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from src.api.main import app
from src.api.dependencies import get_vector_db, get_status_provider, get_record_manager

client = TestClient(app)

@pytest.fixture
def mock_db():
    return MagicMock()

@pytest.fixture
def mock_status_provider():
    mock = MagicMock()
    # Mock the engine/connect behavior for DB queries
    mock_conn = MagicMock()
    mock.engine.connect.return_value.__enter__.return_value = mock_conn
    return mock

@pytest.fixture
def mock_record_manager():
    return MagicMock()

def test_get_documents_endpoint(mock_status_provider):
    # Sobrescribimos la dependencia en la aplicación
    app.dependency_overrides[get_status_provider] = lambda: mock_status_provider
    
    # Mock data para devolver desde la "base de datos"
    user_id = "test_user_123"
    mock_job = {
        "doc_id": "uuid-1",
        "source_path": "test.pdf",
        "status": "completed",
        "created_at": "2024-03-29",
        "file_hash": "hash123"
    }
    
    # El resultado de execute() debe ser algo que podamos iterar y tenga _mapping
    mock_result = MagicMock()
    mock_result._mapping = mock_job
    mock_status_provider.engine.connect.return_value.__enter__.return_value.execute.return_value = [mock_result]
    
    response = client.get(f"/api/debug/document?user_id={user_id}")
    
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == user_id
    assert len(data["documents"]) == 1
    assert data["documents"][0]["doc_id"] == "uuid-1"
    
    # Limpiamos
    app.dependency_overrides.clear()


def test_get_document_chunks_endpoint(mock_db, mock_record_manager):
    app.dependency_overrides[get_vector_db] = lambda: mock_db
    app.dependency_overrides[get_record_manager] = lambda: mock_record_manager
    
    doc_id = "uuid-test-document"
    mock_record_manager.list_keys.return_value = ["chunk_1", "chunk_2"]
    
    # Mock data de ChromaDB
    mock_db.get.return_value = {
        "documents": ["Content 1", "Content 2"],
        "metadatas": [{"title": "T1"}, {"title": "T2"}]
    }
    
    # Aseguramos que no parezca Pinecone para que use .get()
    if hasattr(mock_db, "_index"):
        del mock_db._index

    response = client.get(f"/api/debug/document/{doc_id}/chunks")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["doc_id"] == doc_id
    assert data["total_chunks"] == 2
    assert len(data["chunks"]) == 2
    assert data["chunks"][0]["id"] == "chunk_1"
    assert data["chunks"][0]["page_content"] == "Content 1"
    
    # Limpiamos
    app.dependency_overrides.clear()
