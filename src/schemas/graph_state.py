from typing import TypedDict, Annotated, Sequence, List
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage
from langgraph.graph.message import add_messages
from langchain_core.documents import Document
from pydantic import BaseModel, Field

class GraphState(TypedDict):
    """
    Represents the state of our graph.

    Attributes:
        prompt_version: prompt version being used
        user_info: inyected user's info
        messages: list of messages
    """
    # 'messages' usa el reductor add_messages para acumular el historial
    messages: Annotated[Sequence[BaseMessage], add_messages]
    # Datos inyectados desde el endpoint (no se acumulan, se sobreescriben)
    user_info: dict 
    # Versión del prompt a utilizar
    prompt_version: str
    # Counters for retries (reset on each new query)
    retrieve_retry_count: int
    generate_retry_count: int
    docs_parse_retries: int
    hallucinations_parse_retries: int

class GradeDocuments(BaseModel):
    """Puntuación binaria para verificar relevancia."""
    binary_score: str = Field(description="¿Son los documentos relevantes? 'yes' o 'no'")


class GradeHallucinations(BaseModel):
    """Puntuación binaria para presencia de alucinaciones."""
    binary_score: str = Field(description="¿La respuesta está basada en los hechos? 'yes' o 'no'")


class GradeCompletion(BaseModel):
    """Verifica si el agente completó todas las tareas solicitadas."""
    binary_score: str = Field(description="¿Se completaron todas las tareas? 'yes' o 'no'")
    missing_action: str = Field(description="Descripción de la tarea pendiente")