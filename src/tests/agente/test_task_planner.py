"""
Tests del Nodo Task Planner — Fase 7 Parte 3 (Sesión Optimización)

Valida que el nodo _task_planner genera planes correctos de herramientas,
tanto en modo aislado (sin correr el grafo completo) como en contexto conversacional.
"""
import os
from dotenv import load_dotenv

load_dotenv(override=True)
os.environ["APP_ENV"] = "production"

import pytest
import logging
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from src.service.agent import AgentService
from src.core.llm import LLMFactory
from src.providers.vector_store.factory import VectorStoreFactory
from src.tools.registry import ToolRegistry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def planner_service():
    """Inicializa el AgentService para poder llamar a _task_planner directamente."""
    vector_db = VectorStoreFactory.get_provider().getVectorStore()
    ToolRegistry.set_vector_store(vector_db)
    tools = ToolRegistry.get_agent_tools()
    return AgentService(LLMFactory, tools, None)


def _make_state(user_message: str, history: list = None, summary: str = None) -> dict:
    """
    Construye un GraphState mínimo para pasar al _task_planner.
    
    Args:
        user_message: La consulta del usuario para este turno.
        history: Lista de mensajes previos (AIMessage, HumanMessage) para contexto.
        summary: Texto de resumen de conversación previa (simula SystemMessage de resumen).
    """
    messages = []
    
    # Si hay resumen, lo agregamos primero como SystemMessage
    if summary:
        messages.append(SystemMessage(content=f"Resumen de la conversación hasta ahora: {summary}"))
    
    # Historial previo (turno anterior)
    if history:
        messages.extend(history)
    
    # Mensaje actual del usuario
    messages.append(HumanMessage(content=user_message))
    
    return {
        "messages": messages,
        "user_info": {"user_id": "test_user", "name": "Test"},
        "prompt_version": os.getenv("PROMPT_VERSION"),
        "retrieve_retry_count": 0,
        "generate_retry_count": 0,
        "docs_parse_retries": 0,
        "hallucinations_parse_retries": 0,
        "task_plan": None,
    }


# ---------------------------------------------------------------------------
# Tests de Planificación Aislada (sin grafo completo)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_planner_simple_search(planner_service):
    """Consulta de información local → solo knowledge_base_retriever."""
    state = _make_state("¿Qué discutimos cuando tuvimos la reunión con Google?")
    result = await planner_service._task_planner(state)
    
    plan = result.get("task_plan", [])
    tools_in_plan = [s["tool"] for s in plan]
    
    logger.info(f"Plan para búsqueda local: {tools_in_plan}")
    assert "knowledge_base_retriever" in tools_in_plan, (
        f"Se esperaba knowledge_base_retriever en el plan, se obtuvo: {tools_in_plan}"
    )
    assert "web_search" not in tools_in_plan, (
        f"No se esperaba web_search para consulta de notas locales, se obtuvo: {tools_in_plan}"
    )


@pytest.mark.asyncio
async def test_planner_web_search(planner_service):
    """Consulta de información actual (evento externo) → web_search."""
    state = _make_state("¿Cuál es la formación de Boca Juniors para el partido de hoy?")
    result = await planner_service._task_planner(state)
    
    plan = result.get("task_plan", [])
    tools_in_plan = [s["tool"] for s in plan]
    
    logger.info(f"Plan para búsqueda web: {tools_in_plan}")
    assert "web_search" in tools_in_plan, (
        f"Se esperaba web_search para consulta de evento actual, se obtuvo: {tools_in_plan}"
    )


@pytest.mark.asyncio
async def test_planner_search_and_save(planner_service):
    """Consulta que combina búsqueda local + guardado → ambas herramientas en orden."""
    state = _make_state(
        "Qué frameworks me pidieron usar en la reunión del 15 de marzo de 2026 y guardalos en un documento"
    )
    result = await planner_service._task_planner(state)
    
    plan = result.get("task_plan", [])
    tools_in_plan = [s["tool"] for s in plan]
    
    logger.info(f"Plan para búsqueda + guardado: {tools_in_plan}")
    assert "knowledge_base_retriever" in tools_in_plan, (
        f"Se esperaba knowledge_base_retriever, se obtuvo: {tools_in_plan}"
    )
    assert "save_note_to_knowledge_base" in tools_in_plan, (
        f"Se esperaba save_note_to_knowledge_base, se obtuvo: {tools_in_plan}"
    )
    # Verificar orden: primero buscar, luego guardar
    if "knowledge_base_retriever" in tools_in_plan and "save_note_to_knowledge_base" in tools_in_plan:
        idx_search = tools_in_plan.index("knowledge_base_retriever")
        idx_save = tools_in_plan.index("save_note_to_knowledge_base")
        assert idx_search < idx_save, "La búsqueda debe ir antes del guardado en el plan"


@pytest.mark.asyncio
async def test_planner_web_then_save(planner_service):
    """Búsqueda web + guardado → web_search seguido de save_note_to_knowledge_base."""
    state = _make_state(
        "Buscá en internet los frameworks de Python más usados en 2026 y guardalos en mis notas"
    )
    result = await planner_service._task_planner(state)
    
    plan = result.get("task_plan", [])
    tools_in_plan = [s["tool"] for s in plan]
    
    logger.info(f"Plan para web + guardado: {tools_in_plan}")
    assert "web_search" in tools_in_plan, f"Se esperaba web_search, se obtuvo: {tools_in_plan}"
    assert "save_note_to_knowledge_base" in tools_in_plan, (
        f"Se esperaba save_note_to_knowledge_base, se obtuvo: {tools_in_plan}"
    )


@pytest.mark.asyncio
async def test_planner_conversational(planner_service):
    """Consulta conversacional (saludo) → plan vacío, sin herramientas."""
    state = _make_state("Hola, ¿cómo estás?")
    result = await planner_service._task_planner(state)
    
    plan = result.get("task_plan", [])
    
    logger.info(f"Plan para consulta conversacional: {plan}")
    assert plan == [], (
        f"Se esperaba plan vacío para saludo conversacional, se obtuvo: {plan}"
    )


@pytest.mark.asyncio
async def test_planner_save_only_no_history(planner_service):
    """Pedir guardar sin contexto previo → igual planifica save_note_to_knowledge_base."""
    state = _make_state("Guardá eso en un documento")
    result = await planner_service._task_planner(state)
    
    plan = result.get("task_plan", [])
    tools_in_plan = [s["tool"] for s in plan]
    
    logger.info(f"Plan para guardar sin historial: {tools_in_plan}")
    assert "save_note_to_knowledge_base" in tools_in_plan, (
        f"Se esperaba save_note_to_knowledge_base, se obtuvo: {tools_in_plan}"
    )


# ---------------------------------------------------------------------------
# Tests de Planificación con Contexto Conversacional
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_planner_with_summary_context(planner_service):
    """
    'Anotá eso' con resumen de conversación previa →
    el planner debe resolver la referencia anafórica y planificar solo save.
    """
    summary = (
        "El usuario preguntó sobre frameworks de Python. "
        "El agente respondió que los más populares son FastAPI, LangChain y Django."
    )
    state = _make_state("Anotá eso en mis notas", summary=summary)
    result = await planner_service._task_planner(state)
    
    plan = result.get("task_plan", [])
    tools_in_plan = [s["tool"] for s in plan]
    
    logger.info(f"Plan con resumen previo + 'anotá eso': {tools_in_plan}")
    assert "save_note_to_knowledge_base" in tools_in_plan, (
        f"Se esperaba save_note_to_knowledge_base resolviendo referencia anafórica. Plan: {tools_in_plan}"
    )
    # No debería requerir búsqueda local porque los datos ya están en el resumen
    assert "knowledge_base_retriever" not in tools_in_plan, (
        f"No se esperaba knowledge_base_retriever cuando los datos vienen del resumen. Plan: {tools_in_plan}"
    )


@pytest.mark.asyncio
async def test_planner_with_ai_history(planner_service):
    """
    'Guardá lo que me acabás de decir' con historial de AI reciente →
    el planner debe planificar solo save (los datos ya están en contexto).
    """
    history = [
        HumanMessage(content="¿Cuáles son los mejores frameworks de Python?"),
        AIMessage(content=(
            "Los frameworks más populares de Python son: FastAPI para APIs REST, "
            "Django para aplicaciones web completas, y LangChain para aplicaciones de IA."
        )),
    ]
    state = _make_state("Guardá lo que me acabás de decir en un documento", history=history)
    result = await planner_service._task_planner(state)
    
    plan = result.get("task_plan", [])
    tools_in_plan = [s["tool"] for s in plan]
    
    logger.info(f"Plan con historial AI reciente + 'guardá lo que dijiste': {tools_in_plan}")
    assert "save_note_to_knowledge_base" in tools_in_plan, (
        f"Se esperaba save_note_to_knowledge_base dado el historial previo. Plan: {tools_in_plan}"
    )
