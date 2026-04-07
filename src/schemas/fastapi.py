from pydantic import BaseModel
from typing import List, Any, Optional

class QueryRequest(BaseModel):
    query: str
    user_id: Optional[str] = None
    #top_k: int = 4  # Opcional: cuántos documentos buscar

class QueryResponse(BaseModel):
    #answer: Any  # O el tipo de dato que decidas devolver
    context: List[str] = [] # (Opcional) los fragmentos de texto usados

class AskRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None
    user_info: Optional[dict] = {"user_id": "User"}
    prompt_version: Optional[str] = "rag_v1"

class DeleteRequest(BaseModel):
    doc_id: str
    user_id: str

class FeedbackRequest(BaseModel):
    thread_id: str
    message_id: Optional[str] = None
    user_prompt: Optional[str] = None
    ai_response: Optional[str] = None
    tools_used: Optional[Any] = None
    score: int
    user_correction: Optional[str] = None
