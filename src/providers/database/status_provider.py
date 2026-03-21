from typing import Optional, List
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.core.config import settings
from src.providers.database.models import Base, IngestionJob
import uuid

class StatusProvider:
    def __init__(self):
        # Construct DB URL
        db_url = f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.POSTGRES_DB}"
        self.engine = create_engine(db_url)
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
                if error_msg:
                    job.error_msg = error_msg
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
