import uuid
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import sessionmaker
from src.providers.database.core import get_engine
from src.providers.database.models import Base, Chat, Message

class ChatProvider:
    def __init__(self):
        self.engine = get_engine()
        self.Session = sessionmaker(bind=self.engine)
        self._ensure_table_exists()

    def _ensure_table_exists(self):
        Base.metadata.create_all(self.engine)

    def create_chat(self, user_id: str, title: str, thread_id: Optional[uuid.UUID] = None) -> uuid.UUID:
        if thread_id is None:
            thread_id = uuid.uuid4()
        elif isinstance(thread_id, str):
            thread_id = uuid.UUID(thread_id)
            
        session = self.Session()
        try:
            existing = session.query(Chat).filter(Chat.id == thread_id).first()
            if existing: # Si ya existe un chat con ese ID (idempotencia), solo lo retornamos
                return thread_id

            chat = Chat(
                id=thread_id,
                user_id=user_id,
                title=title
            )
            session.add(chat)
            session.commit()
            return thread_id
        finally:
            session.close()

    def get_user_chats(self, user_id: str) -> List[dict]:
        session = self.Session()
        try:
            chats = session.query(Chat).filter(Chat.user_id == user_id).order_by(Chat.created_at.desc()).all()
            return [
                {
                    "thread_id": str(c.id),
                    "title": c.title,
                    "created_at": c.created_at.isoformat()
                } for c in chats
            ]
        finally:
            session.close()

    def add_message(self, thread_id: uuid.UUID, role: str, content: str, parts: Optional[List[dict]] = None) -> uuid.UUID:
        if isinstance(thread_id, str):
            thread_id = uuid.UUID(thread_id)
            
        msg_id = uuid.uuid4()
        session = self.Session()
        try:
            message = Message(
                id=msg_id,
                chat_id=thread_id,
                role=role,
                content=content,
                parts=parts
            )
            session.add(message)
            session.commit()
            return msg_id
        finally:
            session.close()

    def get_chat_messages(self, thread_id: uuid.UUID) -> List[dict]:
        if isinstance(thread_id, str):
            thread_id = uuid.UUID(thread_id)
            
        session = self.Session()
        try:
            messages = session.query(Message).filter(Message.chat_id == thread_id).order_by(Message.created_at.asc()).all()
            return [
                {
                    "id": str(m.id),
                    "role": m.role,
                    "content": m.content,
                    "parts": m.parts,
                    "created_at": m.created_at.isoformat()
                } for m in messages
            ]
        finally:
            session.close()
