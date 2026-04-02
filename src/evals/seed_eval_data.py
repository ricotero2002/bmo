import os
import sys
import time
from dotenv import load_dotenv

# Asegurar que el directorio raíz esté en el PYTHONPATH para encontrar el paquete 'src'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

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
    user_id = "eval_golden_user"
    
    vector_db = VectorStoreFactory.get_provider().getVectorStore()
    record_manager = RecordManagerFactory.get_manager()
    chunker = AgenticChunker(LLMFactory)
    extractor = ExtractionService()

    logger.info("🚀 Iniciando ingesta del Golden Dataset para Evaluaciones...")
    
    for i, entry in enumerate(GOLDEN_DATASET):
        # Usamos IDs fijos. Así, si corrés el script 2 veces, el RecordManager
        # sobreescribe los viejos en vez de duplicarlos.
        doc_id = f"eval_doc_fixed_{i}"
        
        doc = extractor.create_document(
            text=entry["raw_text"],
            filename=f"{entry['category']}_{i}.txt",
            user_id=user_id
        )
        doc.metadata["source"] = doc_id
        
        chunks = chunker.chunk(entry["raw_text"])
        for c in chunks:
            c.metadata.update({"user_id": user_id, "source": doc_id})
            
        extractor.index_documents(chunks, record_manager, vector_db)
        logger.info(f"✅ Ingestados {len(chunks)} chunks para: {entry['name']}")
    
    logger.info("⏳ Esperando 30 segundos para la consistencia eventual de Pinecone...")
    time.sleep(30)
    
    # --- PRUEBA DE FUEGO ---
    logger.info("🔍 Verificando que Pinecone responda a las consultas...")
    # Hacemos una búsqueda manual simulando lo que hará la Tool
    results = vector_db.similarity_search("Oracle Kafka", k=2, filter={"user_id": user_id})
    
    if results:
        logger.info(f"🎉 ¡Éxito! Pinecone devolvió datos. Ejemplo: {results[0].page_content[:60]}...")
        logger.info("Ya podés correr 'pytest src/evals/test_rag_agentic.py'")
    else:
        logger.error("❌ Pinecone devolvió 0 resultados. Revisar configuración del index.")

if __name__ == "__main__":
    seed_data()
