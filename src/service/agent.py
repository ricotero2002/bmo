import logging
from datetime import date
from typing import Literal
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage, RemoveMessage
from langgraph.graph import StateGraph, START, END
from langgraph.types import RetryPolicy, Command
from langgraph.prebuilt import ToolNode

from src.schemas.graph_state import GraphState, GradeDocuments, GradeHallucinations
from src.service.prompt_loader import PromptLoader
from src.tools.metadata_filter import TOOL_ERROR_PREFIX
from langchain_core.prompts import PromptTemplate
from src.core.telemetry import TelemetryCallbackHandler # <-- Agrega la importación
logger = logging.getLogger(__name__)

MAX_RETRIES = 2

_RETRIEVER_TOOL_NAME = "knowledge_base_retriever"


class AgentService:
    def __init__(self, llm_factory, tools, checkpointer):
        self.llm_factory = llm_factory
        self.model = llm_factory.create(tools=tools).with_config(
            {"callbacks": [TelemetryCallbackHandler()]}
        )
        self.grader_docs_model = llm_factory.create(response_format=GradeDocuments)
        self.grader_hallucinations_model = llm_factory.create(response_format=GradeHallucinations)
        self.tools = tools
        self.checkpointer = checkpointer
        self.graph = self._build_graph()

    def _build_graph(self):
        workflow = StateGraph(GraphState)

        workflow.add_node("agent", self._call_agent)

        # Resiliencia Externa: ToolNode reintentará 3 veces ante caídas de red o API
        tool_retry_policy = RetryPolicy(max_attempts=3, backoff_factor=1.5, jitter=True)
        workflow.add_node("tools", ToolNode(self.tools), retry=tool_retry_policy)

        workflow.add_node("grade_documents", self._grade_documents)
        workflow.add_node("grade_hallucinations", self._grade_hallucinations)
        workflow.add_node("rewrite_query", self._rewrite_query)
        workflow.add_node("cleanup_rag_memory", self._cleanup_rag_memory)
        workflow.add_node("summarize_conversation", self._summarize_conversation)

        workflow.add_edge(START, "agent")

        workflow.add_conditional_edges("agent", self._agent_router)
        workflow.add_conditional_edges("tools", self._tools_router)
        workflow.add_conditional_edges("grade_documents", self._grade_docs_router)
        workflow.add_conditional_edges("grade_hallucinations", self._grade_hallucinations_router)

        workflow.add_edge("rewrite_query", "agent")
        workflow.add_edge("cleanup_rag_memory", "summarize_conversation")
        workflow.add_edge("summarize_conversation", END)

        return workflow.compile(checkpointer=self.checkpointer)

    async def _call_agent(self, state: GraphState):
        prompt_template = PromptLoader.load(state.get("prompt_version", "rag_v1"))
        chain = prompt_template | self.model

        user_info = state.get("user_info") or {"name": "Usuario"}

        messages = list(state["messages"])

        response = await chain.ainvoke({
            "user_name": user_info.get("name", "Usuario"),
            "today": date.today().isoformat(),  # "2026-03-19"
            "messages": messages
        }, config={"tags": ["agent_generation"]})

        # Para que el estado no acumule el mensaje temporal, solo devolvemos la respuesta de la AI
        return {"messages": [response]}

    def _agent_router(self, state: GraphState) -> str:
        messages = state["messages"]
        last_message = messages[-1]

        # Si la LLM decidió llamar a una herramienta
        if last_message.tool_calls:
            return "tools"

        # Si el agente generó contenido vacío (sin texto ni tool_calls)
        # puede suceder cuando no tiene instrucción clara — lo mandamos a resumir o terminar
        if not getattr(last_message, "content", "").strip():
            logger.warning("Agent generated empty content. Routing to summarize.")
            return "cleanup_rag_memory"

        # Si el agente generó texto, verificar si en CUALQUIER parte del historial
        # se usó el retriever — si es así, siempre pasar por grade_hallucinations
        retriever_used = any(
            isinstance(msg, ToolMessage) and msg.name == _RETRIEVER_TOOL_NAME
            for msg in messages
        )
        if retriever_used:
            return "grade_hallucinations"

        # Si la conversación es muy larga, la resumimos
        return "cleanup_rag_memory"

    def _tools_router(self, state: GraphState) -> str:
        messages = state["messages"]
        last_message = messages[-1]

        # El retriever unificado pasa por el grader de documentos
        if getattr(last_message, "name", "") == _RETRIEVER_TOOL_NAME:
            return "grade_documents"

        # Si es el clima u otra tool, volvemos al agente
        return "agent"

    async def _grade_documents(self, state: GraphState):
        """Grades the relevance of retrieved documents."""
        messages = state["messages"]

        question = "pregunta desconocida"
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage) and not msg.content.startswith("Las búsquedas previas no arrojaron"):
                question = msg.content
                break

        docs_text = messages[-1].content

        # Si la tool devolvió un error técnico, forzar reintento inmediato via Command
        if docs_text.startswith(TOOL_ERROR_PREFIX):
            error_detail = docs_text[len(TOOL_ERROR_PREFIX):].strip()
            retry_count = state.get("retrieve_retry_count", 0) + 1

            if retry_count > MAX_RETRIES:
                logger.error("Tool error exceeded max retries. Giving up.")
                return {
                    "retrieve_retry_count": retry_count,
                    "docs_parse_retries": state.get("docs_parse_retries", 0)
                }

            logger.warning(f"Tool returned error (attempt {retry_count}): {error_detail}")
            return Command(
                goto="agent",
                update={
                    "retrieve_retry_count": retry_count,
                    "messages": [
                        HumanMessage(
                            content=(
                                f"[SISTEMA]: La herramienta falló con error: {error_detail}. "
                                "DEBES volver a llamar a la herramienta ahora mismo asegurándote de enviar parámetros válidos."
                            )
                        )
                    ],
                }
            )

        # Caso 2: Reintentos agotados → ordenarle al agente que informe al usuario
        current_retries = state.get("retrieve_retry_count", 0)
        if current_retries >= MAX_RETRIES:
            logger.warning(f"retrieve_retry_count={current_retries} >= MAX_RETRIES. Telling agent to inform user.")
            return Command(
                goto="agent",
                update={
                    "messages": [
                        HumanMessage(
                            content=(
                                "[SISTEMA]: No se encontró información tras múltiples búsquedas. "
                                "Respondí al usuario indicando que no encontraste los datos."
                            )
                        )
                    ],
                }
            )

        grader_model = self.grader_docs_model

        import os
        base_dir = os.path.dirname(os.path.dirname(__file__))
        path = os.path.join(base_dir, "core", "prompts", state.get("prompt_version", "rag_v1"), "grader_document.jinja2")
        with open(path, "r", encoding="utf-8") as f:
            template_text = f.read()

        pt = PromptTemplate.from_template(template_text, template_format="jinja2")
        chain = pt | grader_model

        try:
            res = await chain.ainvoke({"document_context": docs_text, "question": question})
            parse_retries = 0
        except Exception as e:
            parse_retries = state.get("docs_parse_retries", 0) + 1
            if parse_retries > MAX_RETRIES:
                logger.error("GradeDocuments exceeded max parsing retries. Aborting check.")
                return {
                    "retrieve_retry_count": state.get("retrieve_retry_count", 0),
                    "docs_parse_retries": parse_retries
                }

            error_msg = f"Tu evaluación falló con el error: {str(e)}. Debes devolver obligatoriamente un JSON estructurado con la llave 'binary_score' con valor 'yes' o 'no'."
            logger.warning(f"GradeDocuments failed parsing (attempt {parse_retries}). Retrying.")
            return Command(
                goto="grade_documents",
                update={
                    "messages": [SystemMessage(content=error_msg)],
                    "docs_parse_retries": parse_retries
                }
            )

        update_state = {"docs_parse_retries": 0}

        if res.binary_score.lower() == "yes":
            update_state["retrieve_retry_count"] = state.get("retrieve_retry_count", 0)
            return update_state
        else:
            new_count = state.get("retrieve_retry_count", 0) + 1
            update_state["retrieve_retry_count"] = new_count

            # Si se agotaron los reintentos, mandar al agente con instrucción explícita
            if new_count >= MAX_RETRIES:
                logger.warning(f"retrieve_retry_count={new_count} >= MAX_RETRIES. Telling agent to inform user.")
                return Command(
                    goto="agent",
                    update={
                        "retrieve_retry_count": new_count,
                        "docs_parse_retries": 0,
                        "messages": [
                            HumanMessage(
                                content=(
                                    "[SISTEMA]: Los documentos recuperados no son relevantes para la pregunta. "
                                    "DEBES responder al usuario explicando que no encontraste la información."
                                )
                            )
                        ],
                    }
                )

            return update_state

    def _grade_docs_router(self, state: GraphState) -> str:
        count = state.get("retrieve_retry_count", 0)
        # Primera falla (count=1): reescribir la query y darle una oportunidad más al agente
        # Si count=0 (éxito) o count>=MAX_RETRIES (agotado, ya manejado con Command desde _grade_documents)
        # → volver al agente sin instrucción adicional
        if 0 < count < MAX_RETRIES:
            return "rewrite_query"
        return "agent"

    async def _rewrite_query(self, state: GraphState):
        """Si el documento no sirve, enviamos un mensaje a la historia obligando al LLM a reintentar."""
        feedback = HumanMessage(
            content=(
                "[SISTEMA]: Las búsquedas previas no arrojaron información relevante, "
                "incluso tras un intento automático de búsqueda sin filtros adicionales. "
                "DEBES replantear tu 'query' usando palabras clave más amplias, sinónimos "
                "o eliminando filtros de fecha/tipo que puedan ser incorrectos. "
                "Recuerda que la base de datos es sensible a los términos exactos."
            )
        )
        return {"messages": [feedback]}

    async def _grade_hallucinations(self, state: GraphState):
        """Comprueba si la respuesta introdujo datos falsos no presentes en el documento."""
        messages = state["messages"]

        # Encontrar docs (último ToolMessage del retriever)
        docs_text = ""
        for msg in reversed(messages):
            if isinstance(msg, ToolMessage) and msg.name == _RETRIEVER_TOOL_NAME:
                docs_text = msg.content
                break

        # Obtener el último mensaje que debería ser la respuesta del LLM (AIMessage)
        generation = ""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                generation = msg.content
                break

        grader_model = self.grader_hallucinations_model

        import os
        base_dir = os.path.dirname(os.path.dirname(__file__))
        path = os.path.join(base_dir, "core", "prompts", state.get("prompt_version", "rag_v1"), "grader_hallucination.jinja2")
        with open(path, "r", encoding="utf-8") as f:
            template_text = f.read()

        pt = PromptTemplate.from_template(template_text, template_format="jinja2")
        chain = pt | grader_model

        try:
            res = await chain.ainvoke({"document_context": docs_text, "generation": generation})
        except Exception as e:
            parse_retries = state.get("hallucinations_parse_retries", 0) + 1

            if parse_retries > MAX_RETRIES:
                logger.error("GradeHallucinations exceeded max parsing retries. Approving generation.")
                return {
                    "generate_retry_count": state.get("generate_retry_count", 0),
                    "hallucinations_parse_retries": parse_retries
                }

            error_msg = f"Tu evaluación de alucinaciones falló con el error: {str(e)}. Debes devolver un JSON estructurado con 'binary_score' ('yes' o 'no')."
            logger.warning(f"GradeHallucinations failed parsing (attempt {parse_retries}). Retrying.")
            return Command(
                goto="grade_hallucinations",
                update={
                    "messages": [SystemMessage(content=error_msg)],
                    "hallucinations_parse_retries": parse_retries
                }
            )

        update_state = {"hallucinations_parse_retries": 0}

        if res.binary_score.lower() == "yes":
            update_state["generate_retry_count"] = state.get("generate_retry_count", 0)
        else:
            new_count = state.get("generate_retry_count", 0) + 1
            update_state["generate_retry_count"] = new_count
            if new_count < MAX_RETRIES:
                feedback = HumanMessage(
                    content="La respuesta generada contenía alucinaciones o datos que no estaban "
                            "en los documentos. Vuelve a redactarla basándote ESTRICTAMENTE en "
                            "los resultados de la búsqueda."
                )
                update_state["messages"] = [feedback]
            else:
                feedback = AIMessage(
                    content="Lo siento, no pude obtener datos confiables de mi base de "
                            "conocimientos para responder con total seguridad a esa pregunta."
                )
                update_state["messages"] = [feedback]

        return update_state

    def _grade_hallucinations_router(self, state: GraphState) -> str:
        last_msg = state["messages"][-1]
        # Si el último mensaje es el feedback de alucinaciones, volver al agente
        if isinstance(last_msg, HumanMessage) and "alucinaciones" in last_msg.content:
            return "agent"

        # Limpiar mensajes pesados y resumir siempre antes de terminar
        return "cleanup_rag_memory"

    async def _summarize_conversation(self, state: GraphState):
        """Resume los mensajes anteriores de la conversación para no exceder los límites de tokens."""
        # --- FIX PARA TESTS: Si no hay checkpointer, no resumimos ni borramos el historial ---
        if self.checkpointer is None:
            return {}

        messages = state["messages"]

        # Extraemos el resumen anterior si ya existe para concatenarlo
        summary = ""
        for msg in messages:
            if isinstance(msg, SystemMessage) and msg.content.startswith("Resumen de la conversación hasta ahora:"):
                summary = msg.content.replace("Resumen de la conversación hasta ahora: ", "").strip()
                break

        summary_instruction = (
            f"=== TAREA DE RESUMEN ===\n"
            f"Resumen histórico previo: '{summary}'\n\n"
            "Instrucciones:\n"
            "Lee los mensajes de esta conversación. Si hay un 'Resumen histórico previo', combínalo con la información nueva. "
            "Si está vacío, simplemente genera un resumen de lo hablado hasta el momento. "
            "Genera y devuelve ÚNICAMENTE el texto consolidado del resumen, en tercera persona, sin introducciones ni comentarios como 'Aquí tienes...'."
        )

        messages_to_summarize = [m for m in messages if not (isinstance(m, SystemMessage) and m.content.startswith("Resumen"))]

        if not messages_to_summarize:
            return {"messages": []}

        response = await self.model.ainvoke(
            messages_to_summarize + [HumanMessage(content=summary_instruction)]
        )

        last_message = messages[-1] if messages else None

        # Borramos todo exceptuando el ultimo mensaje (el output generado en esta run) 
        # para que quede en el contexto si en la proxima run el usuario pide hacer algo con eso ("análisis de eso")
        delete_messages = [RemoveMessage(id=m.id) for m in messages if m.id != getattr(last_message, 'id', None)]
        new_system_summary = SystemMessage(content=f"Resumen de la conversación hasta ahora: {response.content}")

        return {
            "messages": delete_messages + [new_system_summary]
        }

    async def _cleanup_rag_memory(self, state: GraphState):
        """
        Busca los mensajes de las herramientas (RAG) que contienen los documentos
        pesados y los trunca. Al devolverlos con el mismo ID, LangGraph los
        sobreescribe en la memoria, evitando que Oracle explote.
        """
        # --- FIX PARA TESTS: Si no estamos guardando memoria en BD, no truncamos ---
        if self.checkpointer is None:
            return {}

        messages = state["messages"]
        updates = []

        for m in messages:
            # Buscamos ToolMessages que sean excesivamente largos (ej. > 500 caracteres)
            if isinstance(m, ToolMessage) and len(str(m.content)) > 500:
                # Creamos un clon exacto (mismo ID y tool_call_id) pero vaciamos el contenido
                truncated_msg = ToolMessage(
                    id=m.id,
                    tool_call_id=m.tool_call_id,
                    name=m.name,
                    content="[Documentos recuperados y procesados por el RAG. Contenido removido para optimizar la memoria y evitar límite de Oracle.]"
                )
                updates.append(truncated_msg)

        # Si hubo actualizaciones, las devolvemos para que el reducer sobreescriba
        if updates:
            return {"messages": updates}
        
        return {}

    async def chat(self, message: str, thread_id: str, user_info: dict, prompt_version: str):
        # user_id en configurable para que RunnableConfig lo entregue a las tools (invisible para el LLM)
        user_id = user_info.get("user_id") if user_info else None
        config = {
            "configurable": {
                "thread_id": thread_id,
                "user_id": user_id,
            }
        }

        input_message = {
            "messages": [("user", message)],
            "user_info": user_info,
            "prompt_version": prompt_version,
            "retrieve_retry_count": 0,
            "generate_retry_count": 0,
            "docs_parse_retries": 0,
            "hallucinations_parse_retries": 0
        }

        return await self.graph.ainvoke(input_message, config=config)

    async def astream_chat(self, message: str, thread_id: str, user_info: dict, prompt_version: str):
        """
        Versión streaming del chat. Emite eventos detallados del grafo usando astream_events.
        """
        user_id = user_info.get("user_id") if user_info else None
        config = {
            "configurable": {
                "thread_id": thread_id,
                "user_id": user_id,
            }
        }

        input_message = {
            "messages": [("user", message)],
            "user_info": user_info,
            "prompt_version": prompt_version,
            "retrieve_retry_count": 0,
            "generate_retry_count": 0,
            "docs_parse_retries": 0,
            "hallucinations_parse_retries": 0
        }

        # version="v2" es el estándar actual recomendado por LangChain para eventos
        async for event in self.graph.astream_events(input_message, config=config, version="v2"):
            yield event