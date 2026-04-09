from typing import TypedDict, Annotated, Sequence, List, Optional
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
    # Resúmenes de cada interacción individual (no se guardan en el historial de mensajes)
    run_summaries: Annotated[List[str], lambda x, y: [] if y is None else x + y]
    # Resumen global de la conversación para contexto a largo plazo
    summary: Optional[str]
    # Datos inyectados desde el endpoint (no se acumulan, se sobreescriben)
    user_info: dict 
    # Versión del prompt a utilizar
    prompt_version: str
    # Counters for retries (reset on each new query)
    retrieve_retry_count: int
    generate_retry_count: int
    docs_parse_retries: int
    hallucinations_parse_retries: int
    # Plan de herramientas a ejecutar en este turno (generado por task_planner)
    task_plan: Optional[list]  # List[dict] con {"tool": str, "reason": str, "done": bool}

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


class TaskStep(BaseModel):
    """Un único paso del plan del agente."""
    tool: str = Field(description="Nombre exacto de la herramienta a usar. Uno de: knowledge_base_retriever, web_search, save_note_to_knowledge_base, get_weather_tool. Si no se necesita ninguna herramienta, usar string vacio.")
    reason: str = Field(description="Razón por la que este paso es necesario para cumplir la solicitud del usuario.")


class TaskPlan(BaseModel):
    """Plan estructurado de pasos que el agente debe ejecutar para cumplir la solicitud."""
    steps: List[TaskStep] = Field(description="Lista ordenada de pasos a ejecutar. Puede estar vacía si la consulta es conversacional.")