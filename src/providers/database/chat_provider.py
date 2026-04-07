import uuid
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import sessionmaker
from src.providers.database.core import get_engine
from src.providers.database.models import Base, Chat, Message, ChatFeedback

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

    def add_chat_feedback(
        self,
        thread_id: str,
        score: int,
        message_id: Optional[str] = None,
        user_prompt: Optional[str] = None,
        ai_response: Optional[str] = None,
        tools_used: Optional[dict] = None,
        user_correction: Optional[str] = None
    ) -> uuid.UUID:
        session = self.Session()
        feedback_id = uuid.uuid4()
        try:
            feedback = ChatFeedback(
                id=feedback_id,
                thread_id=thread_id,
                message_id=message_id,
                user_prompt=user_prompt,
                ai_response=ai_response,
                tools_used=tools_used,
                score=score,
                user_correction=user_correction
            )
            session.add(feedback)
            session.commit()
            return feedback_id
        finally:
            session.close()

    def get_all_feedback(self, limit: int = 100) -> List[dict]:
        session = self.Session()
        try:
            feedbacks = session.query(ChatFeedback).order_by(ChatFeedback.timestamp.desc()).limit(limit).all()
            return [
                {
                    "id": str(f.id),
                    "thread_id": f.thread_id,
                    "message_id": f.message_id,
                    "user_prompt": f.user_prompt,
                    "ai_response": f.ai_response,
                    "tools_used": f.tools_used,
                    "score": f.score,
                    "user_correction": f.user_correction,
                    "timestamp": f.timestamp.isoformat()
                } for f in feedbacks
            ]
        finally:
            session.close()

    def delete_chat(self, thread_id: uuid.UUID) -> None:
        if isinstance(thread_id, str):
            thread_id = uuid.UUID(thread_id)
            
        session = self.Session()
        try:
            # Eliminar mensajes primero (no hay cascada definida en base de datos)
            session.query(Message).filter(Message.chat_id == thread_id).delete(synchronize_session=False)
            
            # Eliminar feedback del chat
            session.query(ChatFeedback).filter(ChatFeedback.thread_id == str(thread_id)).delete(synchronize_session=False)

            # Eliminar el chat
            session.query(Chat).filter(Chat.id == thread_id).delete(synchronize_session=False)
            
            session.commit()
        finally:
            session.close()
