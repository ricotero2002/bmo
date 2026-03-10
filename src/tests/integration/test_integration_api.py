'''
import pytest
import warnings
from fastapi.testclient import TestClient
from testcontainers.chroma import ChromaContainer
from langchain_core.messages import AIMessage
from langchain_core.documents import Document
from langchain_classic.indexes import SQLRecordManager

from src.api.main import app
from src.api.dependencies import get_vector_db, get_llm_factory
from src.service.ingestion import ExtractionService

# Ignoramos warnings de librerías terceras como pydub o testcontainers para limpiar el progreso CI
warnings.filterwarnings("ignore", category=RuntimeWarning, module="pydub")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="testcontainers")

# Marcamos todo el módulo como test de integración
pytestmark = pytest.mark.integration

# ==============================================================================
# INTEGRATION TESTS CON CHROMA REAL (Vía Testcontainers) Y LLM MOCKEADO
# ==============================================================================

@pytest.fixture(scope="module")
def chroma_server():
    # Levanta un contenedor Docker efímero con Chroma solo para pruebas
    with ChromaContainer() as chroma:
        server_url = chroma.get_connection_url()
        # Parseamos el host y puerto
        host = server_url.split("://")[1].split(":")[0]
        port = int(server_url.split(":")[2])
        yield host, port

@pytest.fixture
def chroma_vector_store(chroma_server):
    from src.providers.vector_store.chroma_provider import ChromaProvider
    from src.api.dependencies import get_embeddings
    host, port = chroma_server
    provider = ChromaProvider(host=host, port=port, embeddings=get_embeddings())
    return provider.getVectorStore()

@pytest.fixture
def mock_llm_factory():
    """Mockea la fábrica de LLMs para devolver respuestas predecibles y no golpear APIs de Google/OpenAI en CI."""
    class FakeModel:
        async def ainvoke(self, *args, **kwargs):
            return AIMessage(content="Esta es una respuesta mockeada desde el test de integracion.")
            
        def bind_tools(self, *args, **kwargs):
            return self

        def with_structured_output(self, *args, **kwargs):
            # Para el grader que pide binary_score
            class FakeGraderOutput:
                binary_score = "yes"
            
            class FakeGraderModel:
                async def ainvoke(self, *args, **kwargs):
                    return FakeGraderOutput()
            return FakeGraderModel()

    class FakeLLMFactory:
        @staticmethod
        def create(*args, **kwargs):
            return FakeModel()

    return FakeLLMFactory()

@pytest.fixture
def integration_client(chroma_vector_store, mock_llm_factory):
    # Sobrescribimos el db local por el contenedor efimero
    def override_get_vector_db():
        return chroma_vector_store
        
    def override_get_llm_factory():
        return mock_llm_factory
        
    app.dependency_overrides[get_vector_db] = override_get_vector_db
    app.dependency_overrides[get_llm_factory] = override_get_llm_factory
    
    with TestClient(app) as client:
        yield client
        
    app.dependency_overrides = {}

@pytest.fixture
def sqlite_record_manager():
    # Usamos SQLite en memoria para máxima velocidad en los tests del RecordManager
    manager = SQLRecordManager(
        "test_collection", db_url="sqlite:///:memory:"
    )
    manager.create_schema()
    return manager

@pytest.fixture
def extraction_service():
    return ExtractionService()

# ----------------- TESTS -----------------

def test_integration_ingest(integration_client):
    """Testea el endpoint de ingestión real hacia ChromaDB efímero."""
    fake_txt_content = b"Este es un documento de prueba sobre Desarrollo en Unity."
    response = integration_client.post(
        "/api/ingest",
        files={"file": ("integration_test.txt", fake_txt_content, "text/plain")}
    )
    
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["chunks_created"] > 0

def test_integration_ask_agent(integration_client):
    """Testea el workflow completo de LangGraph conectando a BD pero usando LLM Mock."""
    response = integration_client.post(
        "/api/ask",
        json={
            "message": "Que dice el documento de prueba?",
            "thread_id": "integration_test_1"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "response" in data
    assert data["response"] == "Esta es una respuesta mockeada desde el test de integracion."

def test_incremental_indexing_prevents_duplicates(extraction_service, chroma_vector_store, sqlite_record_manager):
    """
    Verifica que al indexar el mismo documento múltiples veces con el mismo contenido,
    el RecordManager evite los duplicados y marque los chunks posteriores como 'skipped'.
    """
    # 1er Intento: Documentos nuevos
    doc1 = Document(page_content="Contenido de prueba muy importante", metadata={"source": "test_doc.pdf"})
    doc2 = Document(page_content="Otra página", metadata={"source": "test_doc.pdf"})
    chunks = [doc1, doc2]
    
    result_1 = extraction_service.index_documents(
        chunks=chunks,
        record_manager=sqlite_record_manager,
        vector_store=chroma_vector_store
    )
    
    # Comprobamos que ambos documentos fueron añadidos
    assert result_1["num_added"] == 2
    assert result_1["num_skipped"] == 0
    assert result_1["num_updated"] == 0
    assert result_1["num_deleted"] == 0
    
    # 2do Intento: Mismo documento
    result_2 = extraction_service.index_documents(
        chunks=chunks,
        record_manager=sqlite_record_manager,
        vector_store=chroma_vector_store
    )
    
    # Comprobamos que ambos documentos fueron ignorados (skipped)
    assert result_2["num_added"] == 0
    assert result_2["num_skipped"] == 2
    assert result_2["num_updated"] == 0
    assert result_2["num_deleted"] == 0

    # 3er Intento: Documento modificado (Simulamos un cambio de chunk y que borramos uno)
    doc_modificado = Document(page_content="Contenido de prueba muy importante modificado", metadata={"source": "test_doc.pdf"})
    chunks_modificados = [doc_modificado]
    
    result_3 = extraction_service.index_documents(
        chunks=chunks_modificados,
        record_manager=sqlite_record_manager,
        vector_store=chroma_vector_store
    )
    
    # Debe haber 1 añadido (el modificado), 0 actualizados, 0 skipped, 
    # y borrado (doc2 ya no existe y doc1 de antes se borra porque su hash mutó)
    assert result_3["num_added"] == 1
    assert result_3["num_deleted"] >= 1 
'''