import pytest
import warnings
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langchain_core.documents import Document
from langchain_classic.indexes import SQLRecordManager

from src.api.main import app
from src.api.dependencies import get_vector_db, get_llm_factory
from src.service.ingestion import ExtractionService
from src.core.config import settings

# Ignoramos warnings de librerías terceras
warnings.filterwarnings("ignore", category=RuntimeWarning, module="pydub")

pytestmark = pytest.mark.integration

@pytest.fixture
def chroma_vector_store():
    """Conecta al ChromaDB que ya está corriendo en el docker-compose."""
    from src.providers.vector_store.chroma_provider import ChromaProvider
    from src.api.dependencies import get_embeddings
    
    # Usamos las configuraciones existentes en el entorno (inyectadas por docker-compose)
    provider = ChromaProvider(
        host=settings.CHROMA_HOST, 
        port=settings.CHROMA_PORT, 
        embeddings=get_embeddings(),
        collection_name=settings.COLLECTION_NAME
    )
    return provider.getVectorStore()

@pytest.fixture
def mock_llm_factory():
    class FakeModel:
        async def ainvoke(self, *args, **kwargs):
            return AIMessage(content="Respuesta mockeada.")
        def bind_tools(self, *args, **kwargs): return self
        def with_structured_output(self, *args, **kwargs):
            class FakeGraderOutput: binary_score = "yes"
            class FakeGraderModel:
                async def ainvoke(self, *args, **kwargs): return FakeGraderOutput()
            return FakeGraderModel()
    class FakeLLMFactory:
        @staticmethod
        def create(*args, **kwargs): return FakeModel()
    return FakeLLMFactory()

@pytest.fixture
def integration_client(chroma_vector_store, mock_llm_factory):
    app.dependency_overrides[get_vector_db] = lambda: chroma_vector_store
    app.dependency_overrides[get_llm_factory] = lambda: mock_llm_factory
    with TestClient(app) as client:
        yield client
    app.dependency_overrides = {}

@pytest.fixture
def sqlite_record_manager():
    manager = SQLRecordManager("test_integration_collection", db_url="sqlite:///:memory:")
    manager.create_schema()
    return manager

@pytest.fixture
def extraction_service():
    return ExtractionService()

# ----------------- TESTS -----------------

def test_integration_ingest_queued(integration_client, mocker):
    """Verifica que el endpoint devuelva 'queued' y llame a la task (mockeada aquí)."""
    # Mockeamos la tarea para no requerir RabbitMQ real en este test de integración de API
    mock_task = mocker.patch("src.api.endpoints.process_document_task.apply_async")
    mock_task.return_value.id = "fake-task-id"
    
    fake_txt_content = b"Contenido de prueba."
    response = integration_client.post(
        "/api/ingest",
        files={"file": ("test.txt", fake_txt_content, "text/plain")}
    )
    
    assert response.status_code == 200
    assert response.json()["status"] == "queued"
    assert response.json()["task_id"] == "fake-task-id"
    assert mock_task.called

def test_integration_ask_agent(integration_client):
    response = integration_client.post(
        "/api/ask",
        json={"message": "Hola", "thread_id": "test_thread"}
    )
    assert response.status_code == 200
    assert "response" in response.json()

def test_incremental_indexing(extraction_service, chroma_vector_store, sqlite_record_manager):
    doc = Document(page_content="Prueba", metadata={"source": "test.pdf"})
    res1 = extraction_service.index_documents([doc], sqlite_record_manager, chroma_vector_store)
    assert res1["num_added"] == 1
    
    res2 = extraction_service.index_documents([doc], sqlite_record_manager, chroma_vector_store)
    assert res2["num_skipped"] == 1