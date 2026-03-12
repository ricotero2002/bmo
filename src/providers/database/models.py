from datetime import datetime
import uuid
from sqlalchemy import Column, String, Integer, DateTime, JSON, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    doc_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, nullable=True) # ID of the owner
    batch_id = Column(UUID(as_uuid=True), nullable=True)
    source_path = Column(String, nullable=False)
    status = Column(String, nullable=False, default="received") # received, queued, processing, indexed, failed, dead
    attempts = Column(Integer, nullable=False, default=0)
    error_msg = Column(Text, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
