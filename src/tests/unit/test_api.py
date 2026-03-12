import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, AsyncMock

from src.api.main import app
from src.api.dependencies import (
    get_embeddings, get_vector_db, get_extraction_service,
    get_record_manager, get_chunking_service, get_llm_factory,
    get_orchestrator
)
from langchain_core.documents import Document
from langchain_community.embeddings import FakeEmbeddings

client = TestClient(app)


# --- Shared Fixtures ---

@pytest.fixture
def mock_embeddings():
    return FakeEmbeddings(size=3072)


@pytest.fixture
def mock_vector_db():
    mock = MagicMock()
    mock_doc = MagicMock()
    mock_doc.page_content = "Contexto simulado devuelto por la DB"
    mock.similarity_search.return_value = [mock_doc]
    return mock


@pytest.fixture
def mock_extraction_service():
    mock = MagicMock()
    mock.extract_text_from_bytes.return_value = "Contenido extraído del archivo simulado"
    mock.create_document.return_value = Document(
        page_content="Contenido extraído del archivo simulado",
        metadata={"source": "simulated_file.pdf"}
    )
    mock.index_documents.return_value = {
        "num_added": 1, "num_updated": 0, "num_skipped": 0, "num_deleted": 0
    }
    return mock


@pytest.fixture
def mock_record_manager():
    return MagicMock()


@pytest.fixture
def mock_chunking_service():
    mock = MagicMock()
    mock.process.return_value = [Document(page_content="Simulated chunk", metadata={"source": "simulated"})]
    return mock


@pytest.fixture
def mock_agent_factory():
    return MagicMock()


@pytest.fixture
def mock_orchestrator():
    """Returns a fully mocked orchestrator with async orchestrate_ingestion."""
    mock = MagicMock()
    mock.orchestrate_ingestion = AsyncMock(return_value={
        "doc_id": "baad0000-0000-0000-0000-000000000000",
        "status": "queued",
        "task_id": "fake-task-id"
    })
    return mock


# --- Tests ---

@pytest.mark.parametrize("filename, mime_type, content", [
    ("test_doc.pdf", "application/pdf", b"%PDF-1.4\n1 0 obj\n"),
    ("test_report.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", b"dummy word bytes"),
    ("test_sheet.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", b"dummy excel bytes"),
    ("test_image.jpg", "image/jpeg", b"dummy image bytes"),
])
def test_ingest_document(mock_orchestrator, filename, mime_type, content):
    """
    Tests the /api/ingest endpoint. Mocks the orchestrator to avoid
    needing a real DB, MinIO, or RabbitMQ connection.
    """
    app.dependency_overrides[get_orchestrator] = lambda: mock_orchestrator

    response = client.post(
        "/api/ingest",
        files={"file": (filename, content, mime_type)}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "queued"
    assert "doc_id" in data
    mock_orchestrator.orchestrate_ingestion.assert_called_once()

    app.dependency_overrides = {}


def test_query_rag(mock_embeddings, mock_vector_db):
    app.dependency_overrides[get_embeddings] = lambda: mock_embeddings
    app.dependency_overrides[get_vector_db] = lambda: mock_vector_db

    response = client.post("/api/query", json={"query": "¿Qué es RAG?"})

    assert response.status_code == 200

    data = response.json()
    assert "context" in data
    assert len(data["context"]) > 0
    assert "Contexto simulado" in data["context"][0]

    # The endpoint passes filter=None when user_id is not provided
    mock_vector_db.similarity_search.assert_called_once_with("¿Qué es RAG?", k=6, filter=None)

    app.dependency_overrides = {}


def test_ingest_batch(mock_orchestrator):
    """Tests the /api/ingest/batch endpoint with two files."""
    app.dependency_overrides[get_orchestrator] = lambda: mock_orchestrator

    files = [
        ("files", ("file1.txt", b"content1", "text/plain")),
        ("files", ("file2.txt", b"content2", "text/plain"))
    ]

    response = client.post("/api/ingest/batch", files=files)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert len(data["processed"]) == 2
    assert mock_orchestrator.orchestrate_ingestion.call_count == 2

    app.dependency_overrides = {}
