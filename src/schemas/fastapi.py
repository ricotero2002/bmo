from pydantic import BaseModel
from typing import List, Any

class QueryRequest(BaseModel):
    query: str
    #top_k: int = 4  # Opcional: cuántos documentos buscar

class QueryResponse(BaseModel):
    #answer: Any  # O el tipo de dato que decidas devolver
    context: List[str] = [] # (Opcional) los fragmentos de texto usados
