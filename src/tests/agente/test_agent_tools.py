import pytest
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from src.core.llm import LLMFactory
from src.service.agent import AgentService
from langgraph.checkpoint.memory import MemorySaver
import os
from dotenv import load_dotenv

load_dotenv(override=True)
@pytest.mark.asyncio
async def test_agent_tool_calling_spy():
    """
    Testea si el agente arma bien la query y pasa bien el config con el user_id.
    Actúa como un 'Spy' sobre la tool knowledge_base_retriever.
    """
    # Variable mutada por el spy para verificar que fue llamado
    spy_called = False

    @tool("knowledge_base_retriever")
    def mock_retriever_spy(
        query: str,
        date_from: str = "",
        source_filter: str = "",
        config: RunnableConfig = None,
    ) -> str:
        """Busca y recupera información relevante de la base de conocimientos personal del usuario."""
        nonlocal spy_called
        spy_called = True
        
        # 1. Validar que el LLM entendió qué buscar
        assert "vacaciones" in query.lower(), f"El agente generó una mala query: {query}"
        
        # 2. Validar que el LLM/LangGraph pasó los metadatos correctos en RunnableConfig
        user_id = config.get("configurable", {}).get("user_id") if config else None
        assert user_id == "user_123", f"El user_id en config es incorrecto: {user_id}"
        
        return "La política de vacaciones permite 15 días hábiles."

    # Setup del Agente con dependencias mockeadas
    mock_tools = [mock_retriever_spy]
    checkpointer = MemorySaver()
    llm_factory = LLMFactory()
    
    agent_service = AgentService(llm_factory=llm_factory, tools=mock_tools, checkpointer=checkpointer)

    # Ejecutar la simulación con user_id "user_123"
    await agent_service.chat(
        message="¿Cuántos días de vacaciones tengo en la empresa?",
        thread_id="test_tool_calling",
        user_info={"user_id": "user_123"},
        prompt_version=os.getenv("PROMPT_VERSION")
    )

    # 3. Validar que el LLM efectivamente invocó la herramienta
    assert spy_called, "El agente decidió no llamar a la herramienta knowledge_base_retriever"
