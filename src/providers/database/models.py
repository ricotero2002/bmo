import os
import json
from datetime import datetime
import uuid
from sqlalchemy import Column, String, Integer, DateTime, Text, Boolean
from sqlalchemy.types import TypeDecorator
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy_utils import StringEncryptedType
from sqlalchemy_utils.types.encrypted.encrypted_type import FernetEngine

Base = declarative_base()


class JSONText(TypeDecorator):
    """
    Tipo JSON portable: almacena como TEXT/CLOB.
    Funciona en Oracle (cualquier versión), PostgreSQL y SQLite.
    La serialización/deserialización es transparente para el código de aplicación.
    """
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            return json.dumps(value)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            return json.loads(value)
        return value


class GUID(TypeDecorator):
    """
    Tipo GUID portable para Oracle.
    Convierte objetos uuid.UUID de Python a Strings de 36 caracteres.
    """
    impl = String
    cache_ok = True

    def load_dialect_impl(self, dialect):
        return dialect.type_descriptor(String(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if not isinstance(value, uuid.UUID):
            return uuid.UUID(value)
        return value


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    doc_id        = Column(GUID, primary_key=True, default=uuid.uuid4)
    user_id       = Column(String(255), nullable=True)
    batch_id      = Column(GUID, nullable=True)
    source_path   = Column(String(1024), nullable=False)
    status        = Column(String(50), nullable=False, default="received")
    attempts      = Column(Integer, nullable=False, default=0)
    error_msg     = Column(Text, nullable=True)
    metadata_json = Column(JSONText, nullable=True)   # TEXT/CLOB — compatible con Oracle 19c+
    created_at    = Column(DateTime, default=datetime.utcnow)
    updated_at    = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    file_hash     = Column(String(256), nullable=True, index=True)

class Chat(Base):
    __tablename__ = "chats"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Message(Base):
    __tablename__ = "messages"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    chat_id = Column(GUID, nullable=False, index=True)
    role = Column(String(50), nullable=False)  # 'user' or 'assistant'
    content = Column(Text, nullable=False)
    parts = Column(JSONText, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class ChatFeedback(Base):
    __tablename__ = "chat_feedback"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    thread_id = Column(String(255), nullable=False, index=True)
    message_id = Column(String(255), nullable=True)
    user_prompt = Column(Text, nullable=True)
    ai_response = Column(Text, nullable=True)
    tools_used = Column(JSONText, nullable=True)
    score = Column(Integer, nullable=False)  # 1 for 👍, -1 for 👎
    user_correction = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

class IngestionSyncState(Base):
    __tablename__ = "ingestion_sync_state"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), nullable=False, index=True)
    source_type = Column(String(50), nullable=False) # e.g., 'notion', 'obsidian'
    last_sync_at = Column(DateTime, nullable=True)
    status = Column(String(50), nullable=False, default="success")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class IngestionBatch(Base):
    __tablename__ = "ingestion_batches"

    batch_id = Column(GUID, primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), nullable=True, index=True)
    status = Column(String(50), nullable=False) # 'success', 'partial_success', 'failed'
    total_files = Column(Integer, nullable=False, default=0)
    doc_ids = Column(JSONText, nullable=True) # Lista de IDs de documentos procesados
    errors = Column(JSONText, nullable=True)  # Detalles de errores si hubo
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# Llave de encriptación AES-256 para tokens sensibles
SECRET_KEY = os.getenv("DB_ENCRYPTION_KEY", "bmo_default_secret_key_32_bytes!!")

class UserIntegration(Base):
    __tablename__ = "user_integrations"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(255), nullable=False, index=True)
    source_type = Column(String(50), nullable=False) # 'notion', 'obsidian', etc.
    
    # Datos encriptados en la base de datos, desencriptados mágicamente por SQLAlchemy
    access_token = Column(StringEncryptedType(String(1024), SECRET_KEY, FernetEngine))
    source_id = Column(StringEncryptedType(String(1024), SECRET_KEY, FernetEngine)) # ID de la BD o Pagina de Notion
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class NotionSyncMetadata(Base):
    """
    Rastrea el estado individual de cada página/bloque descubierto en Notion.
    Permite CDC granular y detección de páginas borradas (orphan detection).
    """
    __tablename__ = "notion_sync_metadata"

    id               = Column(GUID, primary_key=True, default=uuid.uuid4)
    user_id          = Column(String(255), nullable=False, index=True)
    notion_id        = Column(String(255), nullable=False, index=True)  # ID de Notion (página/db)
    parent_id        = Column(String(255), nullable=True)               # ID del padre en el árbol
    object_type      = Column(String(50), nullable=False)               # 'page' | 'database'
    last_edited_time = Column(DateTime, nullable=True)                  # Extraído de la API de Notion
    file_hash        = Column(String(256), nullable=True)               # Hash del contenido (evita reprocessar sin cambios)
    is_archived      = Column(Integer, default=0)                       # 1=eliminado/huérfano, 0=activo (Integer para Oracle compat.)
    created_at       = Column(DateTime, default=datetime.utcnow)
    updated_at       = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
