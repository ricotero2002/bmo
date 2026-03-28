import os
import uuid
import pytest
from dotenv import load_dotenv
from langchain_core.documents import Document
from src.service.ingestion import ExtractionService
from src.providers.vector_store.factory import VectorStoreFactory

# Cargar variables (.env)
load_dotenv(override=True)

# Saltear si no estamos en entorno cloud
pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_ENV") != "cloud",
    reason="Solo se ejecuta con INTEGRATION_ENV=cloud"
)

def test_pinecone_real_ingestion():
    """
    Prueba de integración real: 
    1. Instancia el VectorStore de Pinecone configurado.
    2. Crea un Document con metadatos explícitamente nulos (para verificar la limpieza).
    3. Hace el upsert a Pinecone.
    4. Elimina el documento para no ensuciar la base de datos de producción.
    """
    
    # 1. Obtener el provider de vector store (debería retornar el de Pinecone según el .env)
    try:
        provider = VectorStoreFactory.get_provider()
        vector_store = provider.getVectorStore()
    except Exception as e:
        pytest.fail(f"No se pudo inicializar VectorStoreFactory: {e}")

    # 2. Preparar el documento pasando Nones explícitamente
    service = ExtractionService()
    doc_id = str(uuid.uuid4())
    
    doc = service.create_document(
        text="[TEST_INTEGRACION] Documento generado dinámicamente para probar upsert y omisión de Nones.",
        filename="test_pinecone_upsert.md",
        file_hash=None,       # Peligro original
        user_id=None,         # Peligro original
        page_number=None,     # Peligro original
        chunk_index=0
    )
    
    # Inyectamos el doc_id para identificarlo en el test
    doc.metadata["doc_id"] = doc_id
    
    print(f"\n[+] Intentando subir documento a Pinecone con metadatos limpios: {doc.metadata}")

    # 3. Subir a Pinecone
    try:
        # add_documents devuelve una lista con los IDs (UUIDs) generados o usados en Pinecone
        inserted_ids = vector_store.add_documents([doc])
        assert len(inserted_ids) == 1, "Debería haberse insertado 1 documento"
        print(f"✅ ¡Upsert exitoso en Pinecone! ID insertado: {inserted_ids[0]}")
        
    except Exception as e:
        pytest.fail(f"❌ La ingestión en Pinecone falló (probablemente por metadatos inválidos): {e}")

    # 4. Limpieza (Delete by ID)
    try:
        vector_store.delete(ids=inserted_ids)
        print("✅ Documento de prueba eliminado de Pinecone exitosamente.")
    except Exception as e:
        print(f"⚠️ Advertencia: No se pudo limpiar el documento de prueba {inserted_ids[0]}. Error: {e}")
