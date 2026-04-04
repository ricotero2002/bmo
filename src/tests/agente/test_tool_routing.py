"""
Tests de Enrutamiento de Herramientas — Fase 7 Parte 3

Valida que el agente BMO seleccione la herramienta correcta según el contexto de cada query.
Incluye tests de single-tool y un test multi-tool (búsqueda compleja con fecha + web).
"""
import os
from dotenv import load_dotenv

load_dotenv(override=True)
os.environ["APP_ENV"] = "production"

import pytest
import logging
from datetime import datetime, timezone
from langgraph.checkpoint.memory import MemorySaver

from src.service.agent import AgentService
from src.core.llm import LLMFactory
from src.providers.vector_store.factory import VectorStoreFactory
from src.tools.registry import ToolRegistry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_called_tools(result: dict) -> list[str]:
    """
    Extrae los nombres de las herramientas llamadas por el agente
    inspeccionando los AIMessage.tool_calls del resultado del grafo.
    """
    called_tools = []
    messages = result.get("messages", [])
    for msg in messages:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tool_call in msg.tool_calls:
                called_tools.append(tool_call["name"])
    return called_tools


def _extract_planned_tools(result: dict) -> list[str]:
    """
    Extrae los nombres de las herramientas que el planificador (task_planner)
    decidió que eran necesarias para este turno.
    """
    plan = result.get("task_plan", [])
    if not plan:
        return []
    return [step["tool"] for step in plan]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def agent_service():
    """Inicializa el AgentService con todas las tools registradas (sin checkpointer — single-turn)."""
    vector_db = VectorStoreFactory.get_provider().getVectorStore()
    ToolRegistry.set_vector_store(vector_db)
    tools = ToolRegistry.get_agent_tools()
    service = AgentService(LLMFactory, tools, None)
    return service


@pytest.fixture(scope="module")
def agent_service_with_memory():
    """
    AgentService con MemorySaver — necesario para tests multi-turno donde
    el historial del turno 1 debe persistir para el planner del turno 2.
    """
    vector_db = VectorStoreFactory.get_provider().getVectorStore()
    ToolRegistry.set_vector_store(vector_db)
    tools = ToolRegistry.get_agent_tools()
    service = AgentService(LLMFactory, tools, MemorySaver())
    return service


@pytest.fixture(scope="module")
def agent_service_with_seed(agent_service):
    """
    Inserta un documento sintético con fecha concreta en el vector store
    para el test multi-tool. El documento describe una reunión con frameworks.

    El seed se inserta directamente vía add_texts() para aislar el test
    de datos de producción y no depender de la pipeline de ingesta.
    """
    vector_db = VectorStoreFactory.get_provider().getVectorStore()

    seed_text = (
        "[Contexto Global: Nota de reunión técnica de marzo de 2026.]\n\n"
        "Reunión técnica del 15 de marzo de 2026.\n"
        "Se acordó utilizar LangChain y LlamaIndex como frameworks principales "
        "para la capa de orquestación del nuevo proyecto de IA. "
        "También se mencionó FastAPI para la capa de API y Pinecone como base vectorial."
    )

    # Timestamp exacto del 15 de marzo de 2026 UTC para que date_from funcione
    created_ts = datetime(2026, 3, 15, 10, 0, 0, tzinfo=timezone.utc).timestamp()

    vector_db.add_texts(
        texts=[seed_text],
        metadatas=[{
            "source": "reunion_frameworks_2026-03-15.md",
            "user_id": "test_routing_user",
            "doc_type": "meeting_notes",
            "chunk_index": 0,
            "chunk_type": "agentic",
            "created_at": created_ts,
        }]
    )
    logger.info("Fixture: documento seed para test multi-tool insertado en el vector store.")
    return agent_service


# ---------------------------------------------------------------------------
# Tests Single-Tool
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("query, expected_tool", [
    # 1. Debe usar la base de conocimientos local
    (
        "que fue discutido cuando tuvimos la reunion con google?",
        "knowledge_base_retriever"
    ),
    # 2. Debe buscar en internet (evento actual, sin datos locales posibles)
    (
        "Cual es la formacion de boca en 2026?",
        "web_search"
    ),
    # 3. Debe guardar en la base de conocimientos vía Kafka
    (
        "Qué frameworks me pidieron usar en la reunión del 15 de marzo de 2026 y guardalos en un documento",
        "save_note_to_knowledge_base"
    ),
])
async def test_agent_tool_selection(agent_service, query, expected_tool):
    """
    Valida que el agente selecciona la herramienta correcta para cada tipo de query.
    """
    result = await agent_service.chat(
        message=query,
        thread_id=f"test_routing_{expected_tool}",
        user_info={"user_id": "test_routing_user", "name": "Test User"},
        prompt_version="rag_v3",
    )

    called_tools = _extract_called_tools(result)
    logger.info(f"Query: '{query}' → Herramientas llamadas: {called_tools}")

    assert expected_tool in called_tools, (
        f"Fallo de enrutamiento: Para la query '{query}', se esperaba "
        f"'{expected_tool}' pero se llamaron: {called_tools}"
    )


# ---------------------------------------------------------------------------
# Test Multi-Tool (Búsqueda Compleja con Fecha + Web)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_multi_tool_complex_query(agent_service_with_seed):
    """
    Valida que el agente usa knowledge_base_retriever (con date_from para filtrar
    por la reunión del 15 de marzo 2026) Y web_search en una sola consulta.

    El documento seed contiene: LangChain, LlamaIndex, FastAPI, Pinecone.
    La query fuerza al agente a:
      1. Buscar localmente qué frameworks se pidieron en esa reunión.
      2. Buscar en internet cursos sobre esos frameworks.
    """
    query = (
        "¿Qué frameworks me pidieron usar en la reunión del 15 de marzo de 2026? "
        "Busca en internet cursos o recursos sobre esos frameworks."
    )

    result = await agent_service_with_seed.chat(
        message=query,
        thread_id="test_multi_tool_complex",
        user_info={"user_id": "test_routing_user", "name": "Test User"},
        prompt_version="rag_v3",
    )

    called_tools = _extract_called_tools(result)
    logger.info(f"Test multi-tool → Herramientas llamadas: {called_tools}")

    assert "knowledge_base_retriever" in called_tools, (
        f"Se esperaba que el agente buscara en la base local. "
        f"Herramientas llamadas: {called_tools}"
    )
    assert "web_search" in called_tools, (
        f"Se esperaba que el agente buscara en internet. "
        f"Herramientas llamadas: {called_tools}"
    )

    # Validación de contenido: la respuesta debería mencionar al menos uno de los frameworks
    final_response = result.get("messages", [])[-1].content if result.get("messages") else ""
    frameworks_mentioned = any(
        fw.lower() in final_response.lower()
        for fw in ["LangChain", "LlamaIndex", "FastAPI", "Pinecone"]
    )
    assert frameworks_mentioned, (
        f"La respuesta no menciona ninguno de los frameworks del documento seed. "
        f"Respuesta: {final_response[:300]}"
    )


# ---------------------------------------------------------------------------
# Tests Multi-Turn (Conversaciones Previas)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_multiturn_save_previous_answer(agent_service_with_memory):
    """
    Turno 1: El agente busca en la KB y responde sobre frameworks.
    Turno 2: El usuario pide guardar esa respuesta en un documento.
    
    El planner debe detectar el contexto previo y planificar solo
    save_note_to_knowledge_base (sin necesidad de buscar de nuevo).
    Usa MemorySaver para que el historial del turno 1 persista.
    """
    thread_id = "test_multiturn_save_prev"
    user_info = {"user_id": "test_routing_user", "name": "Test User"}

    # Turno 1: Consulta de información local
    turn1_result = await agent_service_with_memory.chat(
        message="¿Qué discutimos cuando tuvimos la ultima reunion?",
        thread_id=thread_id,
        user_info=user_info,
        prompt_version="rag_v3",
    )
    turn1_tools = _extract_called_tools(turn1_result)
    turn1_plan = _extract_planned_tools(turn1_result)
    logger.info(f"[Turno 1] Herramientas Planificadas: {turn1_plan}")
    logger.info(f"[Turno 1] Herramientas Llamadas: {turn1_tools}")

    # Verificamos que se haya PLANIFICADO la búsqueda local
    assert "knowledge_base_retriever" in turn1_plan, (
        f"El turno 1 debería haber PLANIFICADO knowledge_base_retriever. Plan: {turn1_plan}"
    )

    # Turno 2: El usuario pide guardar la respuesta anterior
    turn2_result = await agent_service_with_memory.chat(
        message="Guardá eso en un documento en mis notas",
        thread_id=thread_id,
        user_info=user_info,
        prompt_version="rag_v3",
    )
    turn2_tools = _extract_called_tools(turn2_result)
    turn2_plan = _extract_planned_tools(turn2_result)
    logger.info(f"[Turno 2] Herramientas Planificadas: {turn2_plan}")
    logger.info(f"[Turno 2] Herramientas Llamadas: {turn2_tools}")

    assert "save_note_to_knowledge_base" in turn2_plan, (
        f"El turno 2 debería haber PLANIFICADO guardar en la KB. Plan: {turn2_plan}"
    )
    '''
    assert "save_note_to_knowledge_base" in turn2_tools, (
        f"El turno 2 debería haber EJECUTADO save_note_to_knowledge_base. Tools: {turn2_tools}"
    )
    '''


@pytest.mark.asyncio
async def test_multiturn_web_search_then_save(agent_service_with_memory):
    """
    Turno 1: El agente busca en internet.
    Turno 2: El usuario pide guardar lo que encontró.
    
    El planner debe detectar el contexto previo con resultados web
    y planificar solo save_note_to_knowledge_base.
    Usa MemorySaver para que el historial del turno 1 persista.
    """
    thread_id = "test_multiturn_web_save"
    user_info = {"user_id": "test_routing_user", "name": "Test User"}

    # Turno 1: Búsqueda web explícita
    turn1_result = await agent_service_with_memory.chat(
        message="Buscá en internet cuáles son los mejores frameworks de Python en 2026",
        thread_id=thread_id,
        user_info=user_info,
        prompt_version="rag_v3",
    )
    turn1_tools = _extract_called_tools(turn1_result)
    turn1_plan = _extract_planned_tools(turn1_result)
    logger.info(f"[Turno 1] Herramientas Planificadas: {turn1_plan}")
    logger.info(f"[Turno 1] Herramientas Llamadas: {turn1_tools}")

    assert "web_search" in turn1_plan, (
        f"El turno 1 debería haber PLANIFICADO web_search. Plan: {turn1_plan}"
    )

    # Turno 2: Guardar lo que encontró en el turno anterior
    turn2_result = await agent_service_with_memory.chat(
        message="Guardá lo que encontraste en mis notas personales",
        thread_id=thread_id,
        user_info=user_info,
        prompt_version="rag_v3",
    )
    turn2_tools = _extract_called_tools(turn2_result)
    turn2_plan = _extract_planned_tools(turn2_result)
    logger.info(f"[Turno 2] Herramientas Planificadas: {turn2_plan}")
    logger.info(f"[Turno 2] Herramientas Llamadas: {turn2_tools}")

    assert "save_note_to_knowledge_base" in turn2_plan, (
        f"El turno 2 debería haber PLANIFICADO guardar en la KB. Plan: {turn2_plan}"
    )
    '''
    assert "save_note_to_knowledge_base" in turn2_tools, (
        f"El turno 2 debería haber EJECUTADO save_note_to_knowledge_base. Tools: {turn2_tools}"
    )
    '''
