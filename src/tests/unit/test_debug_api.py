import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from src.api.main import app
from src.api.dependencies import get_vector_db

client = TestClient(app)

@pytest.fixture
def mock_db():
    return MagicMock()

def test_get_documents_endpoint(mock_db):
    # Sobrescribimos la dependencia en la aplicación
    app.dependency_overrides[get_vector_db] = lambda: mock_db
    
    # Configuramos el mock para devolver datos fixturados
    mock_db.get.return_value = {
        "metadatas": [
            {"source": "doc1.pdf", "chunk_type": "agentic"},
            {"source": "doc2.txt", "chunk_type": "agentic"},
            {"source": "doc1.pdf", "chunk_type": "agentic"}  # duplicado para probar que devuelve únicos
        ]
    }
    
    response = client.get("/api/debug/documents")
    
    assert response.status_code == 200
    data = response.json()
    assert "documents" in data
    
    # Comprobamos que devuelve solo los sources únicos (puede que en distinto orden al ser set)
    assert len(data["documents"]) == 2
    assert "doc1.pdf" in data["documents"]
    assert "doc2.txt" in data["documents"]
    
    # Comprobamos que ChromaDB '.get' se llamó una única vez sin parámetros o con loss parámetros correctos
    mock_db.get.assert_called_once_with(include=["metadatas"])
    
    # Limpiamos
    app.dependency_overrides.clear()


def test_get_document_chunks_endpoint(mock_db):
    app.dependency_overrides[get_vector_db] = lambda: mock_db
    
    # Mock data para devolver chunks espedificos de un documento
    filename = "doc_test.pdf"
    mock_db.get.return_value = {
        "ids": ["chunk_1", "chunk_2"],
        "documents": ["Contenido del chunk 1", "Contenido del chunk 2"],
        "metadatas": [
            {"source": filename, "chunk_title": "Titulo 1"},
            {"source": filename, "chunk_title": "Titulo 2"}
        ]
    }
    
    response = client.get(f"/api/debug/documents/{filename}/chunks")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["filename"] == filename
    assert data["total_chunks"] == 2
    assert len(data["chunks"]) == 2
    
    # Verificamos estructura del primer chunk
    assert data["chunks"][0]["id"] == "chunk_1"
    assert data["chunks"][0]["content"] == "Contenido del chunk 1"
    assert data["chunks"][0]["metadata"]["chunk_title"] == "Titulo 1"
    
    # Verificamos estructura del segundo chunk
    assert data["chunks"][1]["id"] == "chunk_2"
    assert data["chunks"][1]["content"] == "Contenido del chunk 2"
    assert data["chunks"][1]["metadata"]["chunk_title"] == "Titulo 2"
    
    # Verificar que .get() se llamó con los filtros correctos (simulando filtro en ChromaDB)
    mock_db.get.assert_called_once_with(
        where={"source": filename}, 
        include=["metadatas", "documents"]
    )
    
    # Limpiamos
    app.dependency_overrides.clear()
