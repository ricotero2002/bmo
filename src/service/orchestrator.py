import uuid
import io
import hashlib
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from src.providers.database.status_provider import StatusProvider
from src.providers.storage.factory import StorageFactory
from src.workers.tasks import process_document_task
import logging
import os
from src.core.config import settings


logger = logging.getLogger(__name__)

class IngestionOrchestrator:
    def __init__(self, status_provider=None, storage_provider=None):
        self.status_provider = status_provider or StatusProvider()
        self.storage_provider = storage_provider or StorageFactory.get_storage()
        self.allowed_extensions = settings.ALLOWED_EXTENSIONS
        self.max_size = settings.MAX_FILE_SIZE

    def validate_file(self, filename: str, content: Optional[bytes] = None):
        """Valida que el archivo tenga una extensión permitida y no exceda el tamaño."""
        _, ext = os.path.splitext(filename)
        if ext.lower() not in self.allowed_extensions:
            raise ValueError(f"Extensión no permitida: {ext}. Permitidas: {self.allowed_extensions}")
        
        if content and len(content) > self.max_size:
            size_mb = self.max_size / (1024 * 1024)
            raise ValueError(f"El archivo excede el tamaño máximo de {size_mb}MB")

    async def orchestrate_ingestion(
        self, 
        doc_id: uuid.UUID,
        filename: str,
        content: Optional[bytes] = None,
        user_id: Optional[str] = None,
        object_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Orquesta el proceso de ingesta:
        1. Registra en DB.
        2. Sube a Storage (si hay contenido).
        3. Encolar en Celery.
        """
        # 0. Validar archivo
        self.validate_file(filename, content)
        
        try:
            # Calcular hash del contenido para deduplicación
            file_hash = hashlib.sha256(content).hexdigest() if content else None

            # Si el hash ya existe, el archivo no cambió → skip
            if file_hash:
                existing = self.status_provider.get_job_by_hash(file_hash, user_id)
                if existing:
                    return {"status": "already_exists", "doc_id": str(existing["doc_id"])}

            # 1. Crear registro inicial
            job_metadata = {
                "filename": filename,
                "user_id": user_id,
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
            }
            if metadata:
                job_metadata.update(metadata)
                
            self.status_provider.create_job(
                doc_id=doc_id,
                user_id=user_id,
                source_path=filename,
                file_hash=file_hash,
                metadata=job_metadata
            )
            
            # 2. Definir object_name si no viene
            if not object_name:
                object_name = f"{user_id}/{doc_id}" if user_id else str(doc_id)
            
            # 3. Subir a Storage si tenemos el contenido (bytes)
            if content:
                file_stream = io.BytesIO(content)
                self.storage_provider.upload_file(file_stream, object_name=object_name)
            
            # 4. Marcar como queued
            self.status_provider.update_status(doc_id, "queued")
            
            # 5. Delegar al worker
            task = process_document_task.apply_async(
                kwargs={
                    "doc_id": str(doc_id),
                    "filename": filename,
                    "user_id": user_id,
                    "object_name": object_name
                },
                task_id=str(doc_id),
                queue="ingest_q"
            )
            
            return {
                "status": "queued",
                "doc_id": str(doc_id),
                "task_id": task.id
            }
            
        except Exception as e:
            logger.error(f"Error en orquestación para {doc_id}: {e}")
            try:
                self.status_provider.update_status(doc_id, "failed", error_msg=str(e))
            except:
                pass
            raise e
