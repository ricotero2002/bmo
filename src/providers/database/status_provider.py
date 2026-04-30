from typing import Optional, List
import os
import ssl
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.providers.database.models import Base, IngestionJob, IngestionSyncState, IngestionBatch, UserIntegration
import uuid


from src.providers.database.core import get_engine

class StatusProvider:
    def __init__(self):
        self.engine = get_engine()
        self.Session = sessionmaker(bind=self.engine)
        self._ensure_table_exists()



    def _ensure_table_exists(self):
        Base.metadata.create_all(self.engine)

    def create_job(
        self,
        source_path: str,
        user_id: Optional[str] = None,
        doc_id: Optional[uuid.UUID] = None,
        batch_id: Optional[uuid.UUID] = None,
        file_hash: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> uuid.UUID:
        if doc_id is None:
            doc_id = uuid.uuid4()

        session = self.Session()
        try:
            # Idempotencia: Verificar si existe
            existing = session.query(IngestionJob).filter(IngestionJob.doc_id == doc_id).first()
            if existing:
                return doc_id

            job = IngestionJob(
                doc_id=doc_id,
                user_id=user_id,
                batch_id=batch_id,
                source_path=source_path,
                file_hash=file_hash,
                status="received",
                metadata_json=metadata,
            )
            session.add(job)
            session.commit()
            return doc_id
        finally:
            session.close()

    def update_status(self, doc_id: uuid.UUID, status: str, error_msg: Optional[str] = None):
        session = self.Session()
        try:
            job = session.query(IngestionJob).filter(IngestionJob.doc_id == doc_id).first()
            if job:
                job.status = status
                job.error_msg = error_msg  # Siempre escribe (None limpia el error anterior en retries)
                if status == "failed":
                    job.attempts += 1
                session.commit()
        finally:
            session.close()

    def get_job(self, doc_id: uuid.UUID) -> Optional[dict]:
        session = self.Session()
        try:
            job = session.query(IngestionJob).filter(IngestionJob.doc_id == doc_id).first()
            if job:
                return {
                    "doc_id": job.doc_id,
                    "user_id": job.user_id,
                    "batch_id": job.batch_id,
                    "status": job.status,
                    "attempts": job.attempts,
                    "error_msg": job.error_msg,
                    "created_at": job.created_at
                }
            return None
        finally:
            session.close()

    def get_job_by_hash(self, file_hash: str, user_id: Optional[str]) -> Optional[dict]:
        session = self.Session()
        try:
            job = (
                session.query(IngestionJob)
                .filter(IngestionJob.file_hash == file_hash)
                .filter(IngestionJob.user_id == user_id)
                .first()
            )
            if job:
                return {
                    "doc_id": job.doc_id,
                    "user_id": job.user_id,
                    "batch_id": job.batch_id,
                    "status": job.status,
                    "attempts": job.attempts,
                    "error_msg": job.error_msg,
                    "created_at": job.created_at,
                }
            return None
        finally:
            session.close()

    def get_batch_status(self, batch_id: uuid.UUID) -> List[dict]:
        session = self.Session()
        try:
            jobs = session.query(IngestionJob).filter(IngestionJob.batch_id == batch_id).all()
            return [
                {"doc_id": j.doc_id, "status": j.status} for j in jobs
            ]
        finally:
            session.close()

    def update_sync_state(self, user_id: str, source_type: str, status: str = "success", last_sync_at=None) -> None:
        """Actualiza el estado de sincronización (CDC) para un usuario y origen."""
        from datetime import datetime
        session = self.Session()
        try:
            state = session.query(IngestionSyncState).filter(
                IngestionSyncState.user_id == user_id,
                IngestionSyncState.source_type == source_type
            ).first()
            
            sync_time = last_sync_at if last_sync_at is not None else datetime.utcnow()
            
            if state:
                state.last_sync_at = sync_time
                state.status = status
            else:
                state = IngestionSyncState(
                    user_id=user_id,
                    source_type=source_type,
                    last_sync_at=sync_time,
                    status=status
                )
                session.add(state)
            session.commit()
        finally:
            session.close()

    def get_sync_state(self, user_id: str, source_type: str) -> Optional[dict]:
        """Obtiene el estado de sincronización (CDC) para un usuario y origen."""
        session = self.Session()
        try:
            state = session.query(IngestionSyncState).filter(
                IngestionSyncState.user_id == user_id,
                IngestionSyncState.source_type == source_type
            ).first()
            if state:
                return {
                    "last_sync_at": state.last_sync_at,
                    "status": state.status
                }
            return None
        finally:
            session.close()

    def register_integration(self, user_id: str, source_type: str, access_token: str, source_id: str) -> None:
        """Registra una integración de usuario y crea su estado de sincronización inicial en pending."""
        session = self.Session()
        try:
            integration = UserIntegration(
                user_id=user_id,
                source_type=source_type,
                access_token=access_token,
                source_id=source_id
            )
            session.add(integration)
            
            sync_state = IngestionSyncState(
                user_id=user_id,
                source_type=source_type,
                last_sync_at=None,
                status="pending"
            )
            session.add(sync_state)
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def get_sync_targets(self, source_type: str) -> List[dict]:
        """Obtiene los objetivos de sincronización (JOIN de integración y estado) para un source_type dado."""
        session = self.Session()
        try:
            results = (
                session.query(UserIntegration, IngestionSyncState)
                .join(IngestionSyncState, 
                     (UserIntegration.user_id == IngestionSyncState.user_id) & 
                     (UserIntegration.source_type == IngestionSyncState.source_type))
                .filter(UserIntegration.source_type == source_type)
                .all()
            )
            
            targets = []
            for integration, state in results:
                targets.append({
                    "user_id": integration.user_id,
                    "access_token": integration.access_token,
                    "source_id": integration.source_id,
                    "last_sync_at": state.last_sync_at.isoformat() if state.last_sync_at else None
                })
                
            return targets
        finally:
            session.close()

    def save_batch_info(self, batch_id: uuid.UUID, user_id: str, status: str, total_files: int, doc_ids: list, errors: list):
        """Guarda o actualiza la información global de un batch de ingesta."""
        session = self.Session()
        try:
            batch = session.query(IngestionBatch).filter(IngestionBatch.batch_id == batch_id).first()
            if batch:
                batch.status = status
                batch.total_files = total_files
                batch.doc_ids = doc_ids
                batch.errors = errors
            else:
                batch = IngestionBatch(
                    batch_id=batch_id,
                    user_id=user_id,
                    status=status,
                    total_files=total_files,
                    doc_ids=doc_ids,
                    errors=errors
                )
                session.add(batch)
            session.commit()
        finally:
            session.close()

    def get_batch_details(self, batch_id: uuid.UUID) -> Optional[dict]:
        """Devuelve el estado global del batch y el estado individual de cada job/archivo."""
        session = self.Session()
        try:
            batch = session.query(IngestionBatch).filter(IngestionBatch.batch_id == batch_id).first()
            if not batch:
                return None
            
            jobs = session.query(IngestionJob).filter(IngestionJob.batch_id == batch_id).all()
            jobs_info = [
                {
                    "doc_id": j.doc_id,
                    "filename": j.source_path,
                    "status": j.status,
                    "attempts": j.attempts,
                    "error_msg": j.error_msg
                } for j in jobs
            ]

            return {
                "batch_id": batch.batch_id,
                "user_id": batch.user_id,
                "status": batch.status,
                "total_files": batch.total_files,
                "errors": batch.errors,
                "created_at": batch.created_at,
                "jobs": jobs_info
            }
        finally:
            session.close()
