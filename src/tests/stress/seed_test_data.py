import os
import sys
import time
from dotenv import load_dotenv

# Asegurar que el directorio raíz esté en el PYTHONPATH para encontrar el paquete 'src'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

# Cargar variables y forzar Pinecone
load_dotenv(override=True)
os.environ["APP_ENV"] = "production"

import logging
from src.service.chunking import AgenticChunker
from src.service.ingestion import ExtractionService
from src.core.llm import LLMFactory
from src.evals.golden_dataset_v2 import GOLDEN_DATASET
from src.providers.vector_store.factory import VectorStoreFactory
from src.providers.record_manager.factory import RecordManagerFactory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def seed_data():
    # Usamos un usuario específico para las evaluaciones
    user_id = "locust_tester"
    
    vector_db = VectorStoreFactory.get_provider().getVectorStore()
    record_manager = RecordManagerFactory.get_manager()
    chunker = AgenticChunker(LLMFactory)
    extractor = ExtractionService()

    logger.info("🚀 Iniciando ingesta del Golden Dataset para Evaluaciones...")
    
    for i, entry in enumerate(GOLDEN_DATASET):
        # Usamos IDs fijos con prefijo 'eval_doc_fixed_' para que el teardown NO los borre.
        doc_id = f"eval_doc_fixed_{i}"
        
        doc_metadata = {
            "user_id": user_id,
            "source": doc_id,
            "category": entry.get("category", "testing")
        }
        
        # Generamos chunks asumiendo que el chunker ya los devuelve con metadatos base
        chunks = chunker.chunk(entry["raw_text"])
        for c in chunks:
            # Sobreescribimos/Aseguramos los metadatos de usuario e ID de fuente
            c.metadata.update(doc_metadata)
            
        extractor.index_documents(chunks, record_manager, vector_db)
        logger.info(f"✅ Ingestados {len(chunks)} chunks para [GOLDEN]: {entry['name']} (ID: {doc_id})")
    
    logger.info("⏳ Esperando unos segundos para la consistencia eventual...")
    time.sleep(5)
    
    # --- PRUEBA DE FUEGO ---
    logger.info("🔍 Verificando presencia de los documentos en Pinecone...")
    results = vector_db.similarity_search("KEDA crash SASL", k=1, filter={"user_id": user_id})
    
    if results:
        logger.info(f"🎉 ¡Éxito! Recuperado: {results[0].page_content[:100]}...")
    else:
        logger.error("❌ No se recuperaron resultados. ¿Está Pinecone bien configurado?")

if __name__ == "__main__":
    seed_data()
