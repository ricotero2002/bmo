import pytest
from langchain_chroma import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain.indexes import SQLRecordManager
from langchain_core.documents import Document
from src.service.ingestion import PDFService

# Marcamos el test para que se considere de integración
pytestmark = pytest.mark.integration

@pytest.fixture
def memory_vector_store():
    # Usamos embeddings mock o reales si hay API KEY, pero para velocidad usamos falso si es necesario,
    # aunque Chroma requiere función de embedding. Usaremos la real o una dummy si falla.
    # Dado que es un test de integración rápido, usaremos un FakeEmbeddings de langchain_core si está disponible,
    # pero como tenemos GoogleGenerativeAIEmbeddings, dejaremos que intente instanciar, o usamos uno basico.
    from langchain_core.embeddings import FakeEmbeddings
    embeddings = FakeEmbeddings(size=1536)
    
    # Chroma en memoria
    return Chroma(
        collection_name="test_collection",
        embedding_function=embeddings
    )

@pytest.fixture
def sqlite_record_manager():
    # Usamos SQLite en memoria para máxima velocidad en los tests
    manager = SQLRecordManager(
        "test_collection", db_url="sqlite:///:memory:"
    )
    manager.create_schema()
    return manager

@pytest.fixture
def pdf_service():
    return PDFService()

def test_incremental_indexing_prevents_duplicates(pdf_service, memory_vector_store, sqlite_record_manager):
    """
    Verifica que al indexar el mismo documento múltiples veces con el mismo contenido,
    el RecordManager evite los duplicados y marque los chunks posteriores como 'skipped'.
    """
    # 1er Intento: Documentos nuevos
    doc1 = Document(page_content="Contenido de prueba muy importante", metadata={"source": "test_doc.pdf"})
    doc2 = Document(page_content="Otra página", metadata={"source": "test_doc.pdf"})
    chunks = [doc1, doc2]
    
    result_1 = pdf_service.index_documents(
        chunks=chunks,
        record_manager=sqlite_record_manager,
        vector_store=memory_vector_store
    )
    
    # Comprobamos que ambos documentos fueron añadidos
    assert result_1["num_added"] == 2
    assert result_1["num_skipped"] == 0
    assert result_1["num_updated"] == 0
    assert result_1["num_deleted"] == 0
    
    # 2do Intento: Mismo documento
    result_2 = pdf_service.index_documents(
        chunks=chunks,
        record_manager=sqlite_record_manager,
        vector_store=memory_vector_store
    )
    
    # Comprobamos que ambos documentos fueron ignorados (skipped)
    assert result_2["num_added"] == 0
    assert result_2["num_skipped"] == 2
    assert result_2["num_updated"] == 0
    assert result_2["num_deleted"] == 0

    # 3er Intento: Documento modificado (Simulamos un cambio de chunk y que borramos uno)
    doc_modificado = Document(page_content="Contenido de prueba muy importante modificado", metadata={"source": "test_doc.pdf"})
    # El source es el mismo, pero eliminamos doc2 e introducimos un cambio en doc1
    chunks_modificados = [doc_modificado]
    
    result_3 = pdf_service.index_documents(
        chunks=chunks_modificados,
        record_manager=sqlite_record_manager,
        vector_store=memory_vector_store
    )
    
    # Debe haber 1 añadido (el modificado tiene nuevo hash), 0 actualizados, 0 skipped, 
    # y 1 borrado (doc2 ya no existe y doc1 de antes se borra porque su hash no está en el nuevo batch del source)
    # Por el flag cleanup="incremental", debería detectar las eliminaciones del source 'test_doc.pdf'
    assert result_3["num_added"] == 1
    assert result_3["num_deleted"] >= 1  # Debería limpiar doc1 viejo y doc2
