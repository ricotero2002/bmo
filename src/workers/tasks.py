from typing import List, Dict, Any
from celery import Task
from loguru import logger
from .celery_app import celery_app
from src.providers.vector_store.factory import VectorStoreFactory
from src.providers.record_manager.factory import RecordManagerFactory
from src.service.ingestion import ExtractionService
from src.service.chunking import ChunkingService
from src.core.llm import LLMFactory
from src.providers.database.status_provider import StatusProvider
from src.providers.storage.factory import StorageFactory
import uuid
from typing import Optional
import time

# --- Exception Classification ---
class TransientError(Exception):
    """Errors that might succeed if retried (e.g., network, rate limits)."""
    pass

class PermanentError(Exception):
    """Errors that will always fail (e.g., corrupt file, unsupported format)."""
    pass

TRANSIENT_EXCEPTIONS = (
    TransientError,
    ConnectionError,
    TimeoutError,
    # Add specific provider exceptions here as they are identified
)

PERMANENT_EXCEPTIONS = (
    PermanentError,
    FileNotFoundError,
    ValueError, # Usually bad data/format
)

@celery_app.task(
    bind=True,
    name="src.workers.tasks.process_document_task",
    acks_late=True,          # ACK only AFTER successful processing
    reject_on_worker_lost=True,  # Re-queue if worker dies mid-task
    max_retries=5,
    default_retry_delay=60,
)
def process_document_task(self, doc_id: str, filename: str, user_id: Optional[str] = None, object_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Task de Celery para procesar documentos de forma asíncrona.
    1. Descarga el archivo desde MinIO usando el object_name (o doc_id).
    2. Realiza extracción, fragmentación e indexación con metadatos del usuario.
    3. Actualiza el estado en Postgres.
    """
    status_provider = StatusProvider()
    storage_provider = StorageFactory.get_storage()
    job_uuid = uuid.UUID(doc_id)
    
    try:
        # 1. Actualizar estado a 'processing'
        status_provider.update_status(job_uuid, "processing")
        
        # 2. Descargar archivo desde MinIO
        target_object = object_name or doc_id
        logger.info(f"Descargando {filename} (ID: {doc_id}) desde MinIO: {target_object}")
        file_data = storage_provider.download_file(object_name=target_object)
        content = file_data.read()
        
        # 3. Instanciar servicios de procesamiento
        extraction_service = ExtractionService()
        chunking_service = ChunkingService()
        vector_db = VectorStoreFactory.get_provider().getVectorStore()
        record_manager = RecordManagerFactory.get_manager()
        
        # 4. Extraer texto
        logger.info(f"Extraer texto del archivo")
        status_provider.update_status(job_uuid, "extracting")
        text = extraction_service.extract_text_from_bytes(content, filename)
        # Usamos el doc_id como clave primaria lógica en el record manager
        logger.info(f"Creando documento")
        status_provider.update_status(job_uuid, "documenting")
        document = extraction_service.create_document(text, filename)
        document.metadata.update({
            "source": doc_id,
            "user_id": user_id,
            "filename": filename
        })

        # 5. Chunking
        logger.info(f"Procesando chunks para {filename}")
        status_provider.update_status(job_uuid, "chunking")
        chunks = chunking_service.process(document, LLMFactory)
        
        # Aseguramos que todos los chunks hereden metadatos
        for chunk in chunks:
            chunk.metadata.update({
                "source": doc_id,
                "user_id": user_id
            })
        
        # 6. Indexing (Embedding & Storing)
        status_provider.update_status(job_uuid, "embedding")
        logger.info(f"Indexando {len(chunks)} chunks en el vector store")
        result = extraction_service.index_documents(chunks, record_manager, vector_db)
        
        status_provider.update_status(job_uuid, "stored")
        
        # 7. Marcar como completado
        status_provider.update_status(job_uuid, "indexed")
        
        logger.info(f"Procesamiento completado para {filename}")
        return {
            "status": "completed",
            "doc_id": doc_id,
            "chunks_created": len(chunks),
            "index_result": result
        }
    except TRANSIENT_EXCEPTIONS as exc:
        # Exponential backoff: 60s, 120s, 240s, 480s, 960s
        delay = 60 * (2 ** self.request.retries)
        logger.warning(f"Error transitorio para {doc_id}, reintentando ({self.request.retries + 1}/5) en {delay}s: {exc}")
        
        status_provider.update_status(job_uuid, "failed", error_msg=str(exc))
        raise self.retry(exc=exc, countdown=delay)

    except PERMANENT_EXCEPTIONS as exc:
        # Errores permanentes: No reintentar, marcar como 'dead' inmediatamente
        logger.error(f"Error permanente para {doc_id}: {exc}")
        status_provider.update_status(job_uuid, "dead", error_msg=f"PERMANENT_ERROR: {str(exc)}")
        return {"status": "dead", "error": str(exc)}

    except Exception as e:
        # Error genérico: Tratamos como permanente por seguridad si no es clasificado
        # O podrías decidir reintentar si prefieres ser agresivo
        logger.error(f"Error inesperado procesando {filename} (ID: {doc_id}): {e}")
        status_provider.update_status(job_uuid, "dead", error_msg=f"UNEXPECTED_ERROR: {str(e)}")
        return {"status": "dead", "error": str(e)}

@celery_app.task(name="src.workers.tasks.cleanup_expired_cache")
def cleanup_expired_cache():
    """Task to cleanup expired cache entries (placeholder for now)."""
    logger.info("Cleaning up expired cache...")
    # Implementation depends on how cache is structured in Redis
    pass
