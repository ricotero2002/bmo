import pytest
from fastapi.testclient import TestClient
from main import app
from dependencies import get_embeddings
from unittest.mock import MagicMock

client = TestClient(app)

# Mock de Embeddings para no gastar tokens
@pytest.fixture
def mock_embeddings():
    mock = MagicMock()
    mock.embed_query.return_value = [0.1, 0.2, 0.3]
    return mock

def test_ingest_pdf(mock_embeddings):
    # Sobrescribimos la dependencia real por el mock
    app.dependency_overrides[get_embeddings] = lambda: mock_embeddings
    

    with open("src/tests/Freire_Agustin_CV.pdf", "rb") as f:
        response = client.post("/api/ingest", files={"file": ("test.pdf", f, "application/pdf")})
        assert response.status_code == 200
        assert response.json()["status"] == "success"
    # Limpiar overrides
    app.dependency_overrides = {}


def test_query_rag(mock_embeddings):
    app.dependency_overrides[get_embeddings] = lambda: mock_embeddings
    
    response = client.post("/query", json={"query": "¿Qué es RAG?"})
    
    assert response.status_code == 200
    assert "answer" in response.json()
