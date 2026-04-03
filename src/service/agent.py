import logging
from datetime import date
from typing import Literal
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage, RemoveMessage
from langgraph.graph import StateGraph, START, END
from langgraph.types import RetryPolicy, Command
from langgraph.prebuilt import ToolNode

from src.schemas.graph_state import GraphState, GradeDocuments, GradeHallucinations, GradeCompletion
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
        self.checker_completion_model = llm_factory.create(response_format=GradeCompletion)
        self.tools = tools
        self.checkpointer = checkpointer
        self.prompt_loader = PromptLoader  # Permite acceso dinámico a get_prompt
        self.graph = self._build_graph()

    def _build_graph(self):
        workflow = StateGraph(GraphState)

        workflow.add_node("agent", self._call_agent)
        workflow.add_node("agent_router", self._agent_router) # Registrado como nodo para soportar Command
        
        # Resiliencia Externa: ToolNode reintentará 3 veces ante caídas de red o API
        tool_retry_policy = RetryPolicy(max_attempts=3, backoff_factor=1.5, jitter=True)
        workflow.add_node("tools", ToolNode(self.tools), retry=tool_retry_policy)

        workflow.add_node("grade_documents", self._grade_documents)
        workflow.add_node("grade_generation_vs_documents", self._grade_generation_vs_documents_and_question)
        workflow.add_node("grade_task_completion", self._grade_task_completion)
        workflow.add_node("rewrite_query", self._rewrite_query)
        workflow.add_node("cleanup_rag_memory", self._cleanup_rag_memory)
        workflow.add_node("summarize_conversation", self._summarize_conversation)

        workflow.add_edge(START, "agent")
        
        # El agente siempre pasa por el router (ahora un nodo) para decidir el siguiente paso
        workflow.add_edge("agent", "agent_router")

        # Enrutamos inteligentemente después de ejecutar las herramientas
        workflow.add_conditional_edges(
            "tools", 
            self._route_after_tools, 
            {"grade_documents": "grade_documents", "agent": "agent"}
        )
        workflow.add_conditional_edges("grade_documents", self._grade_docs_router)
        workflow.add_conditional_edges("grade_generation_vs_documents", self._grade_hallucinations_router)
        workflow.add_conditional_edges("grade_task_completion", self._grade_task_completion_router)

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

    def _agent_router(self, state: GraphState) -> Command:
        messages = state["messages"]
        last_message = messages[-1]

        # Si la LLM decidió llamar a una herramienta
        if last_message.tool_calls:
            return Command(goto="tools")

        # Si el agente generó contenido vacío (sin texto ni tool_calls)
        # puede suceder cuando no tiene instrucción clara o falla al sintetizar el contexto
        if not getattr(last_message, "content", "").strip():
            # Si hubo un uso previo de herramientas de búsqueda, es un fallo de síntesis (no de herramientas)
            retriever_used = any(
                isinstance(msg, ToolMessage) and msg.name in [_RETRIEVER_TOOL_NAME, "web_search"]
                for msg in messages
            )
            if retriever_used:
                # Si falló la síntesis pero hay información, le damos un "nudge" (codazo)
                # OJO: Solo hacemos esto SI no hemos reintentado demasiado
                retry_count = state.get("generate_retry_count", 0)
                if retry_count < MAX_RETRIES:
                    logger.warning(f"Agent failed to synthesize content. Retry {retry_count + 1}/{MAX_RETRIES}.")
                    # IMPORTANTE: Enviamos un mensaje de sistema MUY claro
                    nudge_msg = HumanMessage(content="[SISTEMA]: Encontraste la información en las herramientas, pero no generaste una respuesta para el usuario. EXPLICACIÓN: Por favor, responde basándote en los documentos encontrados detallando los datos específicos.")
                    return Command(
                        update={
                            "generate_retry_count": retry_count + 1,
                            "messages": [nudge_msg]
                        },
                        goto="agent"
                    )
            
            logger.warning("Agent generated empty content and no retrieval context found. Routing to cleanup.")
            return Command(goto="cleanup_rag_memory")

        # Si el agente generó texto, verificar si en CUALQUIER parte del historial
        # se usó el retriever o búsqueda web — si es así, siempre pasar por validación
        retriever_used = any(
            isinstance(msg, ToolMessage) and msg.name in [_RETRIEVER_TOOL_NAME, "web_search"]
            for msg in messages
        )
        if retriever_used:
            return Command(goto="grade_generation_vs_documents")

        # Si la conversación es muy larga, la resumimos
        return Command(goto="cleanup_rag_memory")

    def _route_after_tools(self, state: GraphState) -> str:
        """Enruta los mensajes dependiendo de qué herramienta se acaba de ejecutar."""
        messages = state["messages"]
        
        # Buscamos qué herramientas se acaban de ejecutar en el último turno
        tool_names = []
        for msg in reversed(messages):
            if msg.type == "tool":
                tool_names.append(msg.name)
            elif msg.type == "ai":
                break # Llegamos al mensaje donde el LLM pidió las tools, paramos de mirar hacia atrás
                
        retrieval_tools = [_RETRIEVER_TOOL_NAME, "web_search"]
        
        # Si usó alguna herramienta de búsqueda de información, hay que evaluar los documentos
        if any(name in retrieval_tools for name in tool_names):
            return "grade_documents"
            
        # Si usó una herramienta de acción (ej. save_note_to_knowledge_base, open_weather_map)
        # No hay documentos que evaluar, volvemos al agente para que genere la respuesta final.
        return "agent"

    def _tools_router(self, state: GraphState) -> str:
        """Helper para retrocompatiblidad si se llama desde otros puntos, redirige a _route_after_tools."""
        return self._route_after_tools(state)

    async def _grade_documents(self, state: GraphState):
        """Evalúa si los documentos (locales o web) recuperados son relevantes."""
        docs_content = ""
        error_detail = ""
        has_search_tool = False

        # Solo buscamos en los mensajes que acaban de ocurrir (último turno)
        for msg in reversed(state["messages"]):
            if msg.type == "tool":
                if msg.name in [_RETRIEVER_TOOL_NAME, "web_search"]:
                    has_search_tool = True
                    docs_content += f"\n{msg.content}"
                    if TOOL_ERROR_PREFIX in str(msg.content):
                        error_detail = str(msg.content)
            elif msg.type == "ai":
                break # Paramos en el mensaje del agente que pidió las tools

        if not has_search_tool:
            return Command(goto="agent")

        if error_detail:
            retry_count = state.get("retrieve_retry_count", 0)
            new_count = retry_count + 1
            if new_count >= MAX_RETRIES:
                logger.warning(f"retrieve_retry_count={new_count} >= MAX_RETRIES. Agent informará.")
                return Command(goto="agent", update={"retrieve_retry_count": new_count})

            return Command(
                goto="agent",
                update={
                    "retrieve_retry_count": new_count,
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

        if "No encontré" in docs_content or "La búsqueda web no arrojó" in docs_content:
            return Command(
                goto="agent",
                update={
                    "messages": [
                        HumanMessage(
                            content=(
                                "[SISTEMA]: La búsqueda no arrojó resultados. "
                                "Informa al usuario o intenta con otra herramienta."
                            )
                        )
                    ],
                }
            )

        prompt = self.prompt_loader.get_prompt(
            "grader_document.jinja2",
            version=state.get("prompt_version", "rag_v3"),
            document_context=docs_content,
            question=state["messages"][0].content
        )
        response = await self.grader_docs_model.ainvoke(prompt)
        
        if response.binary_score == "yes":
            return Command(goto="agent")
        else:
            retries = state.get("docs_parse_retries", 0)
            new_count = retries + 1
            if new_count >= MAX_RETRIES:
                return Command(goto="agent", update={"docs_parse_retries": new_count})

            return Command(
                goto="agent",
                update={
                    "docs_parse_retries": new_count,
                    "messages": [
                        HumanMessage(
                            content=(
                                "[SISTEMA]: Los documentos recuperados no parecen responder a la pregunta inicial. "
                                "Intenta buscar con otros parámetros o usando otra herramienta (ej. web_search si usaste local)."
                            )
                        )
                    ],
                }
            )

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

    async def _grade_generation_vs_documents_and_question(self, state: GraphState):
        """Chequea alucinaciones contra TODAS las fuentes (local + web)."""
        docs_content = ""
        for msg in state["messages"]:
            if msg.type == "tool" and msg.name in [_RETRIEVER_TOOL_NAME, "web_search"]:
                docs_content += f"\n{msg.content}"

        if not docs_content:
            # Si no usó herramientas de búsqueda, no hay qué chequear por alucinación
            return END

        generation = state["messages"][-1].content
        grader_model = self.grader_hallucinations_model

        prompt = self.prompt_loader.get_prompt(
            "grader_hallucination.jinja2",
            version=state.get("prompt_version", "rag_v3"),
            document_context=docs_content,
            generation=generation
        )

        try:
            res = await grader_model.ainvoke(prompt)
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

        # Tras validar alucinaciones, verificamos si faltan tareas por completar
        return "grade_task_completion"

    async def _grade_task_completion(self, state: GraphState):
        """Verifica si el agente completó todas las peticiones basándose ÚNICAMENTE en las herramientas usadas."""
        user_msgs = [m.content for m in state["messages"] if m.type == "human" and not str(m.content).startswith("[SISTEMA]")]
        last_user_msg = user_msgs[-1] if user_msgs else ""
        agent_msg = state["messages"][-1].content

        # Recolectar el historial de herramientas usadas
        used_tools = set()
        for msg in state["messages"]:
            if msg.type == "tool":
                used_tools.add(msg.name)

        if "Lo siento, no pude obtener datos" in agent_msg or "La búsqueda no arrojó resultados" in agent_msg:
            return {"messages": []}

        # --- Lógica Determinista Primero (evita falsos negativos del LLM auditor) ---
        # Detectar si el usuario pidió explícitamente guardar
        save_keywords = ["guardar", "crear nota", "escribir en un documento", "resumir y guardar", "anota", "guarda esto"]
        user_asked_save = any(kw in last_user_msg.lower() for kw in save_keywords)

        # Detectar si el usuario pidió explícitamente buscar en internet
        web_keywords = ["busca en internet", "busca en la web", "googlea", "noticias de hoy", "información actualizada online", "buscar en internet"]
        user_asked_web = any(kw in last_user_msg.lower() for kw in web_keywords)

        # Caso 1: Pidió guardar y no usó la herramienta → fallo claro
        if user_asked_save and "save_note_to_knowledge_base" not in used_tools:
            retries = state.get("generate_retry_count", 0)
            if retries >= MAX_RETRIES:
                return {"messages": [], "generate_retry_count": retries}
            return {
                "generate_retry_count": retries + 1,
                "messages": [HumanMessage(content="[SISTEMA]: Aún no has completado la solicitud del usuario (o alucinaste haberlo hecho sin usar la herramienta). Tarea pendiente detectada por el auditor: Falta usar save_note_to_knowledge_base. DEBES usar la herramienta correspondiente AHORA MISMO y no inventar que ya lo hiciste.")]
            }

        # Caso 2: Pidió buscar en web y no usó la herramienta → fallo claro
        if user_asked_web and "web_search" not in used_tools:
            retries = state.get("generate_retry_count", 0)
            if retries >= MAX_RETRIES:
                return {"messages": [], "generate_retry_count": retries}
            return {
                "generate_retry_count": retries + 1,
                "messages": [HumanMessage(content="[SISTEMA]: Aún no has completado la solicitud del usuario. Tarea pendiente: Falta usar web_search. DEBES usar la herramienta AHORA MISMO.")]
            }

        # Caso 3: Si usó alguna herramienta y no hay tareas pendientes → todo OK
        if used_tools:
            return {"messages": []}

        # Caso 4 (raro): No usó ninguna herramienta → delegar al LLM solo en este caso extremo
        prompt = f"""
        Eres un auditor estricto. El agente NO utilizó ninguna herramienta para responder al usuario.

        Instrucción del usuario: {last_user_msg}
        Respuesta del Agente: {agent_msg}
        Herramientas Ejecutadas: Ninguna

        ¿La pregunta del usuario era conversacional (saludo, agradecimiento, etc.) que NO requería herramientas?
        Si es conversacional: CALIFICA 'yes' y missing_action = 'N/A'.
        Si requería herramientas y el agente no las usó: CALIFICA 'no' y describe la acción faltante.
        """

        response = await self.checker_completion_model.ainvoke(prompt)

        if response.binary_score == "no":
            retries = state.get("generate_retry_count", 0)
            if retries >= MAX_RETRIES:
                return {"messages": [], "generate_retry_count": retries}
            return {
                "generate_retry_count": retries + 1,
                "messages": [HumanMessage(content=f"[SISTEMA]: Aún no has completado la solicitud del usuario (o alucinaste haberlo hecho sin usar la herramienta). Tarea pendiente detectada por el auditor: {response.missing_action}. DEBES usar la herramienta correspondiente AHORA MISMO y no inventar que ya lo hiciste.")]
            }

        return {"messages": []}

    def _grade_task_completion_router(self, state: GraphState) -> str:
        last_msg = state["messages"][-1]
        # Si el supervisor inyectó una instrucción del sistema como HumanMessage, volvemos al agente
        if isinstance(last_msg, HumanMessage) and "[SISTEMA]: Aún no has completado" in last_msg.content:
            return "agent"

        # Si todo está ok, limpiar y terminar
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