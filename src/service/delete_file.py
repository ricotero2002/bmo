import uuid
from typing import Optional, Dict, Any
from src.providers.database.status_provider import StatusProvider
from src.workers.tasks import delete_document_task
import logging


logger = logging.getLogger(__name__)

class DeleteOrchestrator:
    def __init__(self, status_provider=None):
        self.status_provider = status_provider or StatusProvider()

    async def delete_file(
        self, 
        doc_id: uuid.UUID,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:

        try:
            # Marcar el estado preventivamente para evitar consultas
            self.status_provider.update_status(doc_id, "deleting")
            
            # Delegar al worker
            task = delete_document_task.apply_async(
                kwargs={
                    "doc_id": str(doc_id),
                    "user_id": user_id,
                },
                task_id=f"del_{str(doc_id)}",
                queue="ingest_q"
            )
            
            return {
                "status": "delete_queued",
                "doc_id": str(doc_id),
                "task_id": task.id
            }
            
        except Exception as e:
            logger.error(f"Error en orquestación de borrado para {doc_id}: {e}")
            try:
                self.status_provider.update_status(doc_id, "delete_failed", error_msg=str(e))
            except:
                pass
            raise e
