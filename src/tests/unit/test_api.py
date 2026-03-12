import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from src.api.main import app
from src.api.dependencies import get_embeddings, get_vector_db, get_extraction_service, get_record_manager, get_chunking_service, get_llm_factory
from langchain_core.documents import Document

client = TestClient(app)

# 1. Mock de Embeddings
from langchain_community.embeddings import FakeEmbeddings

@pytest.fixture
def mock_embeddings():
    # Usamos FakeEmbeddings para un mock más realista como indica la doc oficial
    return FakeEmbeddings(size=3072)

# 2. Mock robusto de Base de datos (Chroma)
@pytest.fixture
def mock_vector_db():
    mock = MagicMock()
    
    # Para .add_documents(), no necesitamos que devuelva nada específico
    mock.add_documents.return_value = None
    
    # Para similarity_search(), Langchain suele devolver una lista de objetos Document
    mock_doc = MagicMock()
    mock_doc.page_content = "Contexto simulado devuelto por la DB"
    mock.similarity_search.return_value = [mock_doc]
    
    return mock

# 3. Mock de Extraction Service
@pytest.fixture
def mock_extraction_service():
    mock = MagicMock()
    mock.extract_text_from_bytes.return_value = "Contenido extraído del archivo simulado"
    
    # En lugar de un MagicMock, usamos un objeto Document real o le asignamos un dict a metadata
    mock.create_document.return_value = Document(
        page_content="Contenido extraído del archivo simulado",
        metadata={"source": "simulated_file.pdf"}
    )
    
    # Simula el resultado de index_documents
    mock.index_documents.return_value = {
        "num_added": 1,
        "num_updated": 0,
        "num_skipped": 0,
        "num_deleted": 0
    }
    return mock

# 4. Mock de Record Manager
@pytest.fixture
def mock_record_manager():
    return MagicMock()

# 5. Mock de Chunking Service
@pytest.fixture
def mock_chunking_service():
    mock = MagicMock()
    # Simula devolver una lista con el mismo documento
    mock.process.return_value = [Document(page_content="Simulated chunk", metadata={"source": "simulated"})]
    return mock

# 6. Mock de Agent Factory
@pytest.fixture
def mock_agent_factory():
    return MagicMock()

@pytest.mark.parametrize("filename, mime_type, content", [
    ("test_doc.pdf", "application/pdf", b"%PDF-1.4\n1 0 obj\n"),
    ("test_report.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", b"dummy word bytes"),
    ("test_sheet.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", b"dummy excel bytes"),
    ("test_image.jpg", "image/jpeg", b"dummy image bytes"),
])
def test_ingest_document(mocker, mock_embeddings, mock_vector_db, mock_extraction_service, mock_record_manager, mock_chunking_service, mock_agent_factory, filename, mime_type, content):
    # Mock de la tarea de Celery
    mock_task = mocker.patch("src.api.endpoints.process_document_task.apply_async")
    mock_task.return_value.id = "fake-task-id"
    
    # Aislar endpoints sobreescribiendo las dependencias
    app.dependency_overrides[get_embeddings] = lambda: mock_embeddings
    app.dependency_overrides[get_vector_db] = lambda: mock_vector_db
    app.dependency_overrides[get_extraction_service] = lambda: mock_extraction_service
    app.dependency_overrides[get_record_manager] = lambda: mock_record_manager
    app.dependency_overrides[get_chunking_service] = lambda: mock_chunking_service
    app.dependency_overrides[get_llm_factory] = lambda: mock_agent_factory
    
    # Ejecutar Endpoint
    response = client.post(
        "/api/ingest",
        files={"file": (filename, content, mime_type)}
    )
    
    # Validar resultados HTTP
    assert response.status_code == 200
    assert response.json()["status"] == "queued"
    assert "task_id" in response.json()
    assert response.json()["task_id"] == "fake-task-id"
    
    # Verificar que la tarea se llamó
    assert mock_task.called
    
    # Limpiar override
    app.dependency_overrides = {}

#arreglar
def test_query_rag(mock_embeddings, mock_vector_db):
    app.dependency_overrides[get_embeddings] = lambda: mock_embeddings
    app.dependency_overrides[get_vector_db] = lambda: mock_vector_db
    
    response = client.post("/api/query", json={"query": "\u00bfQu\u00e9 es RAG?"})
    
    assert response.status_code == 200
    
    data = response.json()
    assert "context" in data
    assert len(data["context"]) > 0 
    assert "Contexto simulado" in data["context"][0]
    
    mock_vector_db.similarity_search.assert_called_once_with("¿Qué es RAG?", k=6)
    
    app.dependency_overrides = {}
