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

logger = logging.getLogger(__name__)

MAX_RETRIES = 2

_RETRIEVER_TOOL_NAME = "knowledge_base_retriever"


class AgentService:
    def __init__(self, llm_factory, tools, checkpointer):
        self.llm_factory = llm_factory
        self.model = llm_factory.create(tools=tools)
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
        workflow.add_node("summarize_conversation", self._summarize_conversation)

        workflow.add_edge(START, "agent")

        workflow.add_conditional_edges("agent", self._agent_router)
        workflow.add_conditional_edges("tools", self._tools_router)
        workflow.add_conditional_edges("grade_documents", self._grade_docs_router)
        workflow.add_conditional_edges("grade_hallucinations", self._grade_hallucinations_router)

        workflow.add_edge("rewrite_query", "agent")

        return workflow.compile(checkpointer=self.checkpointer)

    async def _call_agent(self, state: GraphState):
        prompt_template = PromptLoader.load(state.get("prompt_version", "rag_v1"))
        chain = prompt_template | self.model

        user_info = state.get("user_info") or {"name": "Usuario"}

        messages = list(state["messages"])
        if messages and isinstance(messages[-1], ToolMessage):
            messages.append(HumanMessage(content="Por favor extrae la respuesta del resultado de la herramienta y contesta mi pregunta. No devuelvas un mensaje vacío."))

        response = await chain.ainvoke({
            "user_name": user_info.get("name", "Usuario"),
            "today": date.today().isoformat(),  # "2026-03-19"
            "messages": messages
        })

        # Para que el estado no acumule el mensaje temporal, solo devolvemos la respuesta de la AI
        return {"messages": [response], "generated": response}

    def _agent_router(self, state: GraphState) -> str:
        messages = state["messages"]
        last_message = messages[-1]

        # Si la LLM decidió llamar a una herramienta
        if last_message.tool_calls:
            return "tools"

        # Si el agente generó contenido vacío (sin texto ni tool_calls)
        # puede suceder cuando no tiene instrucción clara — lo mandamos a resumir o terminar
        if not getattr(last_message, "content", "").strip():
            logger.warning("Agent generated empty content. Routing to summarize or END.")
            if len(messages) > 4:
                return "summarize_conversation"
            return END

        # Si el agente generó texto, verificar si en CUALQUIER parte del historial
        # se usó el retriever — si es así, siempre pasar por grade_hallucinations
        retriever_used = any(
            isinstance(msg, ToolMessage) and msg.name == _RETRIEVER_TOOL_NAME
            for msg in messages
        )
        if retriever_used:
            return "grade_hallucinations"

        # Si la conversación es muy larga, la resumimos
        if len(messages) > 6:
            return "summarize_conversation"

        return END

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
                    "messages": [HumanMessage(
                        content=(
                            f"La herramienta `knowledge_base_retriever` falló con un error técnico: {error_detail}. "
                            "DEBES volver a llamar a la herramienta ahora mismo. "
                            "Asegurate de que el parámetro 'query' no esté vacío — "
                            "describí el contenido que querés buscar con palabras clave."
                        )
                    )],
                }
            )

        # Caso 2: Reintentos agotados → ordenarle al agente que informe al usuario
        current_retries = state.get("retrieve_retry_count", 0)
        if current_retries >= MAX_RETRIES:
            logger.warning(f"retrieve_retry_count={current_retries} >= MAX_RETRIES. Telling agent to inform user.")
            return Command(
                goto="agent",
                update={
                    "messages": [HumanMessage(
                        content=(
                            "No se encontró información relevante tras múltiples búsquedas. "
                            "Respondí al usuario de forma honesta: "
                            "indícale que no encontraste los datos solicitados en la base de conocimientos. "
                            "Luégo, predícale al usuario qué información adicional podría ayudarte a encontrar lo que busca "
                            "(por ejemplo: el nombre exacto del archivo, una fecha más precisa, etc.)."
                        )
                    )],
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
                        "messages": [HumanMessage(
                            content=(
                                "No se encontró información relevante en la base de conocimientos tras múltiples búsquedas. "
                                "DEBES responder al usuario ahora mismo (sin usar más herramientas): "
                                "explicale que no encontraste los datos que buscaba, "
                                "y preguntale qué información adicional puede darte para ayudarte a buscarlo "
                                "(por ejemplo: un término de búsqueda diferente, el nombre exacto del archivo, "
                                "o un período de tiempo más preciso)."
                            )
                        )],
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
            content="Las búsquedas previas no arrojaron información relevante. "
                    "Modifica tu razonamiento o parámetros de búsqueda y vuelve a intentar "
                    "usar la herramienta `knowledge_base_retriever` con palabras clave "
                    "diferentes o cambiando los filtros (date_from, source_filter)."
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

        generation = state.get("generated", AIMessage(content="")).content

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
                update_state["generated"] = feedback

        return update_state

    def _grade_hallucinations_router(self, state: GraphState) -> str:
        last_msg = state["messages"][-1]
        # Si el último mensaje es el feedback de alucinaciones, volver al agente
        if isinstance(last_msg, HumanMessage) and "alucinaciones" in last_msg.content:
            return "agent"

        # Si la conversación es muy larga, resumir antes de terminar
        if len(state["messages"]) > 6:
            return "summarize_conversation"

        return END

    async def _summarize_conversation(self, state: GraphState):
        """Resume los mensajes anteriores de la conversación para no exceder los límites de tokens."""
        summary = state.get("summary", "")
        messages = state["messages"]
        if len(messages) <= 6:
            return {"messages": []}

        summary_message = (
            f"This is summary of conversation to date: {summary}\n\n"
            "Extend the summary by taking into account the new messages above."
        )

        messages_to_summarize = messages[:-2]

        response = await self.model.ainvoke(
            messages_to_summarize + [HumanMessage(content=summary_message)]
        )

        delete_messages = [RemoveMessage(id=m.id) for m in messages_to_summarize]
        new_system_summary = SystemMessage(content=f"Resumen de la conversación hasta ahora: {response.content}")

        return {
            "summary": response.content,
            "messages": delete_messages + [new_system_summary]
        }

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