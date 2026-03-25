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
    start_time = time.time()
    
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
        
        # --- METRIC: Extraction Duration ---
        ext_start = time.time()
        text = extraction_service.extract_text_from_bytes(content, filename)
        duration = time.time() - ext_start
        
        from src.core.telemetry import metrics_registry
        metrics_registry.extraction_duration.record(duration, {"file_type": filename.split('.')[-1] if '.' in filename else "unknown"})
        # ----------------------------------

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
        
        # --- METRIC: Success ---
        metrics_registry.docs_processed.add(1, {"status": "success", "file_type": filename.split('.')[-1] if '.' in filename else "unknown"})
        # -----------------------

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
        raise exc

    except Exception as e:
        # Error genérico: Tratamos como permanente por seguridad si no es clasificado
        # O podrías decidir reintentar si prefieres ser agresivo
        logger.error(f"Error inesperado procesando {filename} (ID: {doc_id}): {e}")
        status_provider.update_status(job_uuid, "dead", error_msg=f"UNEXPECTED_ERROR: {str(e)}")
        raise e

@celery_app.task(name="src.workers.tasks.cleanup_expired_cache")
def cleanup_expired_cache():
    """Task to cleanup expired cache entries (placeholder for now)."""
    logger.info("Cleaning up expired cache...")
    # Implementation depends on how cache is structured in Redis
    pass

@celery_app.task(
    bind=True,
    name="src.workers.tasks.delete_document_task",
    acks_late=True,          # ACK only AFTER successful processing
    reject_on_worker_lost=True,  # Re-queue if worker dies mid-task
    max_retries=5,
    default_retry_delay=60,
)
def delete_document_task(self, doc_id: str, user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Tarea de Celery para eliminar documentos de forma asíncrona e idempotente.
    1. Borra del Vector Store usando las keys del RecordManager.
    2. Borra el archivo físico de Storage.
    3. Marca como 'deleted' en la base de datos SQL.
    """
    status_provider = StatusProvider()
    storage_provider = StorageFactory.get_storage()
    job_uuid = uuid.UUID(doc_id)
    
    try:
        status_provider.update_status(job_uuid, "deleting")

        # 1. Vector Store & Record Manager
        vector_db = VectorStoreFactory.get_provider().getVectorStore()
        record_manager = RecordManagerFactory.get_manager()
        
        # Obtenemos las keys de los chunks asociados a este doc_id
        keys = record_manager.list_keys(group_ids=[doc_id])
        if keys:
            logger.info(f"Borrando {len(keys)} chunks del Vector Store para el documento {doc_id}")
            try:
                vector_db.delete(ids=keys)
            except Exception as e:
                logger.warning(f"Error al borrar del Vector Store (puede que ya no existan): {e}")
            
            # Quitar referencias del RecordManager
            record_manager.delete_keys(keys)
        else:
            logger.info(f"No se encontraron chunks en RecordManager para {doc_id}.")

        # 2. Object Storage (MinIO/S3)
        target_object = f"{user_id}/{doc_id}" if user_id else doc_id
        logger.info(f"Borrando archivo {target_object} del Storage")
        try:
            storage_provider.delete_file(target_object)
        except Exception as e:
            logger.warning(f"Error al borrar del Storage (o ya fue borrado): {e}")

        # 3. Base de Datos (Marcar como DELETED definitivo)
        status_provider.update_status(job_uuid, "deleted")
        
        logger.info(f"Borrado exitoso distribuido para {doc_id}")
        return {
            "status": "deleted",
            "doc_id": doc_id,
        }

    except TRANSIENT_EXCEPTIONS as exc:
        delay = 60 * (2 ** self.request.retries)
        logger.warning(f"Error transitorio borrando {doc_id}, reintentando ({self.request.retries + 1}/5) en {delay}s: {exc}")
        status_provider.update_status(job_uuid, "delete_failed", error_msg=str(exc))
        raise self.retry(exc=exc, countdown=delay)

    except PERMANENT_EXCEPTIONS as exc:
        logger.error(f"Error permanente borrando {doc_id}: {exc}")
        status_provider.update_status(job_uuid, "dead", error_msg=f"PERMANENT_ERROR: {str(exc)}")
        raise exc

    except Exception as e:
        logger.error(f"Error inesperado borrando {doc_id}: {e}")
        status_provider.update_status(job_uuid, "dead", error_msg=f"UNEXPECTED_ERROR: {str(e)}")
        raise e
