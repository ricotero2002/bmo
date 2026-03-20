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
    thread_id: str
    user_info: Optional[dict] = {"user_id": "User"}
    prompt_version: Optional[str] = "rag_v1"
