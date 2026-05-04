from typing import Optional, List
import os
import ssl
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.providers.database.models import Base, IngestionJob, IngestionSyncState, IngestionBatch, UserIntegration, NotionSyncMetadata
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
        """Registra o actualiza una integración de usuario y asegura su estado de sincronización."""
        session = self.Session()
        try:
            # 1. Upsert Integración
            integration = session.query(UserIntegration).filter(
                UserIntegration.user_id == user_id,
                UserIntegration.source_type == source_type,
                UserIntegration.source_id == source_id
            ).first()

            if integration:
                integration.access_token = access_token
            else:
                integration = UserIntegration(
                    user_id=user_id,
                    source_type=source_type,
                    access_token=access_token,
                    source_id=source_id
                )
                session.add(integration)
            
            # 2. Upsert Sync State
            sync_state = session.query(IngestionSyncState).filter(
                IngestionSyncState.user_id == user_id,
                IngestionSyncState.source_type == source_type
            ).first()

            if not sync_state:
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

    def update_integration(self, user_id: str, source_type: str, access_token: Optional[str] = None, source_id: Optional[str] = None) -> bool:
        """Actualiza los datos de una integración existente."""
        session = self.Session()
        try:
            integration = session.query(UserIntegration).filter(
                UserIntegration.user_id == user_id,
                UserIntegration.source_type == source_type
            ).first()
            
            if not integration:
                return False
                
            if access_token is not None:
                integration.access_token = access_token
            if source_id is not None:
                integration.source_id = source_id
                
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def delete_integration(self, user_id: str, source_type: str, source_id: Optional[str] = None) -> bool:
        """Elimina una integración específica o todas las de un tipo para un usuario."""
        session = self.Session()
        try:
            query = session.query(UserIntegration).filter(
                UserIntegration.user_id == user_id,
                UserIntegration.source_type == source_type
            )
            if source_id:
                query = query.filter(UserIntegration.source_id == source_id)
            
            integrations = query.all()
            if not integrations:
                return False
                
            for integration in integrations:
                session.delete(integration)
            
            # Si ya no quedan integraciones de este tipo, borrar el sync state
            remaining = session.query(UserIntegration).filter(
                UserIntegration.user_id == user_id,
                UserIntegration.source_type == source_type
            ).count()
            
            if remaining == 0:
                session.query(IngestionSyncState).filter(
                    IngestionSyncState.user_id == user_id,
                    IngestionSyncState.source_type == source_type
                ).delete()

            session.commit()
            return True
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

    # --- Notion CDC Metadata ---

    def upsert_notion_page_metadata(
        self,
        user_id: str,
        notion_id: str,
        parent_id: Optional[str],
        object_type: str,
        last_edited_time,
        file_hash: Optional[str] = None,
        is_archived: int = 0,
    ) -> None:
        """Crea o actualiza el registro de metadatos de sincronización de una página/db de Notion."""
        from datetime import datetime as dt
        session = self.Session()
        try:
            record = session.query(NotionSyncMetadata).filter(
                NotionSyncMetadata.user_id == user_id,
                NotionSyncMetadata.notion_id == notion_id,
            ).first()

            if record:
                record.parent_id = parent_id
                record.object_type = object_type
                record.last_edited_time = last_edited_time
                record.file_hash = file_hash
                record.is_archived = is_archived
                record.updated_at = dt.utcnow()
            else:
                record = NotionSyncMetadata(
                    user_id=user_id,
                    notion_id=notion_id,
                    parent_id=parent_id,
                    object_type=object_type,
                    last_edited_time=last_edited_time,
                    file_hash=file_hash,
                    is_archived=is_archived,
                )
                session.add(record)

            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def get_notion_page_metadata(self, user_id: str, notion_id: str) -> Optional[dict]:
        """Devuelve el registro de metadatos para una página/db de Notion, o None si no existe."""
        session = self.Session()
        try:
            record = session.query(NotionSyncMetadata).filter(
                NotionSyncMetadata.user_id == user_id,
                NotionSyncMetadata.notion_id == notion_id,
            ).first()
            if record:
                return {
                    "notion_id": record.notion_id,
                    "parent_id": record.parent_id,
                    "object_type": record.object_type,
                    "last_edited_time": record.last_edited_time,
                    "file_hash": record.file_hash,
                    "is_archived": record.is_archived,
                }
            return None
        finally:
            session.close()

    def get_all_notion_page_ids_for_user(self, user_id: str) -> List[str]:
        """Devuelve todos los notion_id activos (no archivados) de un usuario. Usado en orphan detection."""
        session = self.Session()
        try:
            records = session.query(NotionSyncMetadata.notion_id).filter(
                NotionSyncMetadata.user_id == user_id,
                NotionSyncMetadata.is_archived == 0,
            ).all()
            return [r.notion_id for r in records]
        finally:
            session.close()

    def mark_notion_pages_archived(self, user_id: str, notion_ids: List[str]) -> None:
        """Marca como archivados (huérfanos) los notion_ids que ya no se encuentran en el árbol."""
        from datetime import datetime as dt
        if not notion_ids:
            return
        session = self.Session()
        try:
            session.query(NotionSyncMetadata).filter(
                NotionSyncMetadata.user_id == user_id,
                NotionSyncMetadata.notion_id.in_(notion_ids),
            ).update(
                {"is_archived": 1, "updated_at": dt.utcnow()},
                synchronize_session=False,
            )
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def get_all_notion_metadata_for_user(self, user_id: str) -> List[dict]:
        """Devuelve todos los registros de metadatos de Notion para un usuario."""
        session = self.Session()
        try:
            records = session.query(NotionSyncMetadata).filter(
                NotionSyncMetadata.user_id == user_id
            ).all()
            return [
                {
                    "notion_id": r.notion_id,
                    "parent_id": r.parent_id,
                    "object_type": r.object_type,
                    "last_edited_time": r.last_edited_time.isoformat() if r.last_edited_time else None,
                    "file_hash": r.file_hash,
                    "is_archived": r.is_archived,
                    "updated_at": r.updated_at.isoformat() if r.updated_at else None
                } for r in records
            ]
        finally:
            session.close()

    def reset_notion_metadata(self, user_id: str) -> None:
        """Borra todos los metadatos de sincronización de Notion para un usuario."""
        session = self.Session()
        try:
            session.query(NotionSyncMetadata).filter(
                NotionSyncMetadata.user_id == user_id
            ).delete()
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def batch_upsert_notion_metadata(self, user_id: str, updates: List[dict]) -> None:
        """Actualiza múltiples registros de metadatos de Notion en una sola transacción."""
        from datetime import datetime as dt
        session = self.Session()
        try:
            for up in updates:
                notion_id = up["notion_id"]
                record = session.query(NotionSyncMetadata).filter(
                    NotionSyncMetadata.user_id == user_id,
                    NotionSyncMetadata.notion_id == notion_id,
                ).first()

                # Parse last_edited_time if it's a string
                last_edited = up["last_edited_time"]
                if isinstance(last_edited, str):
                    from dateutil.parser import parse
                    last_edited = parse(last_edited)

                if record:
                    record.parent_id = up.get("parent_id")
                    record.object_type = up["object_type"]
                    record.last_edited_time = last_edited
                    record.file_hash = up.get("file_hash")
                    record.is_archived = up.get("is_archived", 0)
                    record.updated_at = dt.utcnow()
                else:
                    record = NotionSyncMetadata(
                        user_id=user_id,
                        notion_id=notion_id,
                        parent_id=up.get("parent_id"),
                        object_type=up["object_type"],
                        last_edited_time=last_edited,
                        file_hash=up.get("file_hash"),
                        is_archived=up.get("is_archived", 0),
                    )
                    session.add(record)
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()
