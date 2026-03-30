import os
import pytest
from dotenv import load_dotenv
from src.service.ingestion import ExtractionService
from src.providers.vector_store.factory import VectorStoreFactory
from src.providers.record_manager.factory import RecordManagerFactory

# Cargar variables (.env)
load_dotenv(override=True)

# Saltear si no estamos en entorno cloud
pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_ENV") != "cloud",
    reason="Solo se ejecuta con INTEGRATION_ENV=cloud"
)

def test_full_indexation_flow():
    """
    Prueba el flujo completo del Agente de Ingestión:
    1. Genera chunks de prueba.
    2. Usa el RecordManager (Oracle) y VectorStore (Pinecone) REALES.
    3. Verifica que el primer upsert inserta nuevos elementos.
    4. Verifica que un segundo upsert (con el mismo contenido) es ignorado (Idempotencia).
    """
    # 1. Inicializar Providers reales
    try:
        vector_store = VectorStoreFactory.get_provider().getVectorStore()
        record_manager = RecordManagerFactory.get_manager()
    except Exception as e:
        pytest.fail(f"Fallo inicializando providers para la prueba: {e}")

    service = ExtractionService()
    
    # 2. Crear Documentos de prueba (Simulando chunks procesados por LangChain)
    test_filename = "test_flujo_integracion.md"
    doc1 = service.create_document(
        text="Este es un chunk de prueba A para probar el flujo completo.",
        filename=test_filename,
        chunk_index=0
    )
    doc2 = service.create_document(
        text="Este es un chunk de prueba B para probar el flujo completo.",
        filename=test_filename,
        chunk_index=1
    )
    docs = [doc1, doc2]

    # 3. PRIMERA PASADA: Debería insertar los 2 documentos
    print("\n[+] Ejecutando primera indexación (Upsert a Pinecone & Oracle)...")
    try:
        result_primera_vez = service.index_documents(docs, record_manager, vector_store)
        print(f"Resultado 1: {result_primera_vez}")
        assert result_primera_vez["num_added"] == 2, "Deberían haberse añadir 2 documentos nuevos."
    except Exception as e:
        pytest.fail(f"La primera indexación falló: {e}")

    # 4. SEGUNDA PASADA: Debería ignorarlos (Demuestra que OracleSQLRecordManager funcionó)
    print("\n[+] Ejecutando segunda indexación (Mismos documentos)...")
    try:
        result_segunda_vez = service.index_documents(docs, record_manager, vector_store)
        print(f"Resultado 2: {result_segunda_vez}")
        assert result_segunda_vez["num_added"] == 0, "No debería añadir duplicados."
        assert result_segunda_vez["num_skipped"] == 2, "Debería haber omitido los 2 documentos existentes."
    except Exception as e:
        pytest.fail(f"La segunda indexación falló: {e}")

    # 5. LIMPIEZA: Usamos las funcionalidades de vector_store para limpiar los tests
    print("\n[+] Limpiando Pinecone...")
    try:
        # Pinecone permite borrar por filtrado de metadatos
        vector_store.delete(filter={"source": test_filename})
        print("✅ Documentos de prueba eliminados exitosamente.")
    except Exception as e:
        print(f"⚠️ Advertencia: Fallo en la limpieza final: {e}")
