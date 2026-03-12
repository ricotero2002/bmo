from typing import List, Dict, Any
from celery import Task
from loguru import logger
from .celery_app import celery_app
from src.providers.vector_store.factory import VectorStoreFactory
from src.providers.record_manager.factory import RecordManagerFactory
from src.service.ingestion import ExtractionService
from src.service.chunking import ChunkingService
from src.core.llm import LLMFactory

@celery_app.task(
    bind=True,
    name="src.workers.tasks.process_document_task",
    max_retries=3,
    default_retry_delay=30
)
def process_document_task(self, content_b64: str, filename: str) -> Dict[str, Any]:
    """
    Task de Celery para procesar documentos de forma asíncrona.
    Realiza extracción, fragmentación (chunking) e indexación.
    """
    try:
        import base64
        content = base64.b64decode(content_b64)
        
        logger.info(f"Iniciando procesamiento de {filename}")
        
        # 1. Instanciar servicios
        extraction_service = ExtractionService()
        chunking_service = ChunkingService()
        vector_db = VectorStoreFactory.get_provider().getVectorStore()
        record_manager = RecordManagerFactory.get_manager()
        
        # 2. Extraer texto
        text = extraction_service.extract_text_from_bytes(content, filename)
        document = extraction_service.create_document(text, filename)
        
        # 3. Chunking (Usa LLM si es necesario)
        logger.info(f"Procesando chunks para {filename}")
        chunks = chunking_service.process(document, LLMFactory)
        
        # 4. Indexar en la base de datos vectorial
        logger.info(f"Indexando {len(chunks)} chunks en el vector store")
        result = extraction_service.index_documents(chunks, record_manager, vector_db)
        
        logger.info(f"Procesamiento completado para {filename}")
        return {
            "status": "completed",
            "filename": filename,
            "chunks_created": len(chunks),
            "index_result": result
        }
    except Exception as e:
        logger.error(f"Error procesando {filename}: {e}")
        raise self.retry(exc=e)

@celery_app.task(name="src.workers.tasks.cleanup_expired_cache")
def cleanup_expired_cache():
    """Task to cleanup expired cache entries (placeholder for now)."""
    logger.info("Cleaning up expired cache...")
    # Implementation depends on how cache is structured in Redis
    pass
