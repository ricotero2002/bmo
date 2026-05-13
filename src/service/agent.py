import logging
import os
from datetime import date
from typing import Literal
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage, RemoveMessage
from langgraph.graph import StateGraph, START, END
from langgraph.types import RetryPolicy, Command
from langgraph.prebuilt import ToolNode
from src.schemas.graph_state import GraphState, GradeDocuments, GradeHallucinations, GradeCompletion, TaskPlan, TaskStep
from src.service.prompt_loader import PromptLoader
from src.tools.metadata_filter import TOOL_ERROR_PREFIX
from langchain_core.prompts import PromptTemplate
logger = logging.getLogger(__name__)

MAX_RETRIES = 2

_RETRIEVER_TOOL_NAME = "knowledge_base_retriever"

# Categorías para enrutamiento inteligente
READ_TOOLS = {_RETRIEVER_TOOL_NAME, "web_search", "open_weather_map"}
ACTION_TOOLS = {"save_note_to_knowledge_base"}



class AgentService:
    def __init__(self, llm_factory, tools, checkpointer):
        self.llm_factory = llm_factory
        self.model = llm_factory.create(tools=tools)
        self.grader_docs_model = llm_factory.create_judge(response_format=GradeDocuments)
        self.grader_hallucinations_model = llm_factory.create_judge(response_format=GradeHallucinations)
        self.checker_completion_model = llm_factory.create_lite(response_format=GradeCompletion)
        self.task_planner_model = llm_factory.create_planner(response_format=TaskPlan)
        self.tools = tools
        self.checkpointer = checkpointer
        self.prompt_loader = PromptLoader  # Permite acceso dinámico a get_prompt
        self.graph = self._build_graph()

    def _build_graph(self):
        workflow = StateGraph(GraphState)

        workflow.add_node("agent", self._call_agent)
        workflow.add_node("agent_router", self._agent_router) # Registrado como nodo para soportar Command
        workflow.add_node("task_planner", self._task_planner)  # Planificador inicial por turno
        
        # Resiliencia Externa: ToolNode reintentará 3 veces ante caídas de red o API
        tool_retry_policy = RetryPolicy(max_attempts=3, backoff_factor=1.5, jitter=True)
        workflow.add_node("tools", ToolNode(self.tools), retry=tool_retry_policy)

        workflow.add_node("grade_documents", self._grade_documents)
        workflow.add_node("grade_generation_vs_documents", self._grade_generation_vs_documents_and_question)
        workflow.add_node("grade_task_completion", self._grade_task_completion)
        workflow.add_node("rewrite_query", self._rewrite_query)
        workflow.add_node("cleanup_rag_memory", self._cleanup_rag_memory)
        workflow.add_node("summarize_run", self._summarize_run)
        workflow.add_node("summarize_conversation", self._summarize_conversation)

        workflow.add_edge(START, "task_planner")
        workflow.add_edge("task_planner", "agent")
        
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
        workflow.add_edge("cleanup_rag_memory", "summarize_run")
        workflow.add_edge("summarize_run", "summarize_conversation")
        workflow.add_edge("summarize_conversation", END)

        return workflow.compile(checkpointer=self.checkpointer)

    async def _call_agent(self, state: GraphState):
        prompt_template = PromptLoader.load(state.get("prompt_version", "rag_v1"))
        chain = prompt_template | self.model

        user_info = state.get("user_info") or {"name": "Usuario"}
        summary = state.get("summary", "")
        
        # 1. Preparar mensajes y sanitizar para evitar errores 400 de NVIDIA (Unterminated strings)
        raw_messages = list(state["messages"])
        sanitized_messages = []
        for m in raw_messages:
            content = m.content
            if isinstance(content, str):
                # FIX: Si un mensaje termina en \, NVIDIA NIM puede fallar con Unterminated String
                if content.endswith("\\"):
                    content += " "
            sanitized_messages.append(m.copy(update={"content": content}))

        # 2. Inyectar Resumen si el prompt es viejo
        if state.get("prompt_version") != "rag_v4" and summary:
            sanitized_messages = [SystemMessage(content=f"Resumen histórico de la conversación: {summary}")] + sanitized_messages

        # 3. NUDGE: Si se acaba de usar save_note_to_knowledge_base, obligar al agente a mostrar el output completo
        last_tool_msg = next((m for m in reversed(sanitized_messages) if getattr(m, "type", "") == "tool"), None)
        if last_tool_msg and getattr(last_tool_msg, "name", "") == "save_note_to_knowledge_base":
            sanitized_messages.append(SystemMessage(content="[SISTEMA]: Has guardado una nota. DEBES mostrar el contenido completo de lo que guardaste al usuario en tu respuesta para confirmar la acción."))

        response = await chain.ainvoke({
            "user_name": user_info.get("name", "Usuario"),
            "today": date.today().isoformat(),
            "global_summary": summary,
            "run_summaries": state.get("run_summaries", []),
            "messages": sanitized_messages
        }, config={"tags": ["agent_generation"]})

        # Para que el estado no acumule el mensaje temporal, solo devolvemos la respuesta de la AI
        return {"messages": [response]}

    async def _task_planner(self, state: GraphState):
        """Analiza el mensaje del usuario y genera un plan estructurado de herramientas a ejecutar."""
        messages = state["messages"]
        
        # Obtener el último mensaje real del usuario
        user_msgs = [m for m in messages if m.type == "human" and not str(m.content).startswith("[SISTEMA]")]
        last_user_msg = user_msgs[-1].content if user_msgs else ""
        
        # Construir contexto previo para referencias anafóricas ("guarda lo anterior", "busca eso")
        context_parts = []
        
        # 1. Si hay un resumen de la conversación, incluirlo
        for msg in messages:
            if isinstance(msg, SystemMessage) and str(msg.content).startswith("Resumen de la conversación hasta ahora:"):
                context_parts.append(f"Resumen de conversación previa: {msg.content}")
                break
        
        # 2. Si no hay resumen, incluir los últimos 2 mensajes del agente como contexto
        if not context_parts:
            ai_history = [m for m in messages if m.type == "ai" and not m.tool_calls and m.content]
            recent_ai = ai_history[-2:]
            if recent_ai:
                context_parts.append("Respuestas anteriores del agente:")
                for m in recent_ai:
                    preview = str(m.content)[:300]
                    context_parts.append(f"  - {preview}")
        
        context_str = "\n".join(context_parts) if context_parts else "No hay conversación previa."

        try:
            prompt_text = self.prompt_loader.get_prompt(
                "task_planner.jinja2",
                version=state.get("prompt_version", "rag_v3"),
                global_summary=state.get("summary", ""),
                run_summaries=state.get("run_summaries", []),
                context_str=context_str,
                user_message=last_user_msg,
            )
            result = await self.task_planner_model.ainvoke([HumanMessage(content=prompt_text)])
            plan_steps = [{"tool": step.tool, "reason": step.reason, "done": False} for step in result.steps if step.tool]
            logger.info(f"Task plan generated: {[s['tool'] for s in plan_steps]}")
            return {"task_plan": plan_steps}
        except Exception as e:
            logger.warning(f"Task planner failed: {e}. Proceeding without a plan.")
            return {"task_plan": []}

    async def _agent_router(self, state: GraphState) -> Command:
        messages = state["messages"]
        last_message = messages[-1]

        # Si la LLM decidió llamar a una herramienta
        if getattr(last_message, "tool_calls", None):
            return Command(goto="tools")

        # --- NUEVO: ESCUDO PROTECTOR PARA ERRORES 400/500 EN NVIDIA ---
        # Si la llamada falló (ej: JSON roto por límite de tokens)
        if getattr(last_message, "invalid_tool_calls", None):
            retry_count = state.get("generate_retry_count", 0)
            if retry_count < MAX_RETRIES:
                logger.warning(f"Agent generated invalid tool calls. Retry {retry_count + 1}/{MAX_RETRIES}.")
                nudge_msg = HumanMessage(content="[SISTEMA]: Tu llamada a la herramienta fue inválida o se cortó por exceder el límite de texto. Por favor, intenta de nuevo siendo más conciso en los parámetros.")
                return Command(
                    update={
                        "generate_retry_count": retry_count + 1,
                        # VITAL: Usamos RemoveMessage para borrar el mensaje corrupto del historial.
                        # Así NVIDIA no intentará parsearlo en el siguiente turno y no tirará error 500.
                        "messages": [RemoveMessage(id=last_message.id), nudge_msg]
                    },
                    goto="agent"
                )

        # Si el agente generó contenido vacío (sin texto ni tool_calls)
        # puede suceder cuando no tiene instrucción clara o falla al sintetizar el contexto
        # Identificar el ultimo turno
        last_human_idx = -1
        for i, msg in enumerate(messages):
            if msg.type == "human" and not str(msg.content).startswith("[SISTEMA]"):
                last_human_idx = i
        current_turn_msgs = messages[last_human_idx + 1:] if last_human_idx != -1 else messages

        msg_content = getattr(last_message, "content", "")
        if isinstance(msg_content, list):
            msg_content = "".join(str(c) for c in msg_content)
        
        # --- RECOVERY: Detectar si el modelo intentó llamar herramientas usando código (hallucinación) ---
        # "tool_code" o "default_api" o nombres de herramientas seguidos de paréntesis
        hallucinated_code = any(kw in msg_content for kw in ["tool_code", "default_api", f"{_RETRIEVER_TOOL_NAME}("])
        if not getattr(last_message, "tool_calls", None) and hallucinated_code:
            retry_count = state.get("generate_retry_count", 0)
            if retry_count < MAX_RETRIES:
                logger.warning(f"Agent hallucinated tool code instead of native call. Retry {retry_count + 1}/{MAX_RETRIES}.")
                nudge_msg = HumanMessage(content="[SISTEMA]: Has intentado llamar a una herramienta usando código Python (tool_code). ERROR: NO debes usar código. Debes usar la función nativa de llamada a herramienta (tool_call) proporcionada. Por favor, intenta de nuevo.")
                return Command(
                    update={
                        "generate_retry_count": retry_count + 1,
                        "messages": [nudge_msg]
                    },
                    goto="agent"
                )
        
        if not msg_content.strip():
            # Si hubo un uso previo de herramientas de búsqueda, es un fallo de síntesis (no de herramientas)
            retriever_used = any(
                msg.type == "tool" and msg.name in [_RETRIEVER_TOOL_NAME, "web_search"]
                for msg in current_turn_msgs
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

        # Identificar las herramientas usadas en este turno en ORDEN de ejecución
        tools_used_in_turn = [msg.name for msg in current_turn_msgs if msg.type == "tool"]

        if tools_used_in_turn:
            # Miramos cuál fue la ÚLTIMA herramienta ejecutada antes de que el LLM generara este texto
            last_tool = tools_used_in_turn[-1]
            
            if last_tool in READ_TOOLS:
                # Intención: Síntesis de información.
                # El agente acaba de leer documentos, debemos evitar que invente datos.
                return Command(goto="grade_generation_vs_documents")
            else:
                # Intención: Confirmación de acción (ej. ACTION_TOOLS como guardar_nota).
                # El agente está confirmando que ejecutó un comando. No tiene sentido 
                # evaluar alucinaciones aquí, vamos directo a evaluar completitud.
                return Command(goto="grade_task_completion")
        
        # Si no se usó ninguna herramienta (charla casual) o ya pasó por síntesis,
        # verificamos si el plan está completo antes de limpiar memoria.
        return Command(goto="grade_task_completion")

    async def _route_after_tools(self, state: GraphState) -> str:
        """Enruta los mensajes dependiendo de qué herramienta se acaba de ejecutar."""
        messages = state["messages"]
        
        # Buscamos qué herramientas se acaban de ejecutar en el último turno
        tool_names = []
        for msg in reversed(messages):
            if msg.type == "tool":
                tool_names.append(msg.name)
            elif msg.type == "ai":
                break # Llegamos al mensaje donde el LLM pidió las tools, paramos de mirar hacia atrás
                
        # Si usó alguna herramienta de lectura de información, hay que evaluar la relevancia
        if any(name in READ_TOOLS for name in tool_names):
            return "grade_documents"
            
        # Si usó una herramienta de acción pura o no hubo herramientas de lectura
        # Volvemos al agente para que genere la respuesta final o confirmación.
        return "agent"

    async def _tools_router(self, state: GraphState) -> str:
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
                if msg.name in READ_TOOLS:
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

    async def _grade_docs_router(self, state: GraphState) -> str:
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
        """Chequea alucinaciones contra fuentes (local + web) del TURNO ACTUAL."""
        messages = state["messages"]
        last_human_idx = -1
        for i, msg in enumerate(messages):
            if msg.type == "human" and not str(msg.content).startswith("[SISTEMA]"):
                last_human_idx = i
        current_turn_msgs = messages[last_human_idx + 1:] if last_human_idx != -1 else messages

        docs_content = ""
        for msg in current_turn_msgs:
            if msg.type == "tool" and msg.name in READ_TOOLS:
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

    async def _grade_hallucinations_router(self, state: GraphState) -> str:
        last_msg = state["messages"][-1]
        # Si el último mensaje es el feedback de alucinaciones, volver al agente
        if isinstance(last_msg, HumanMessage) and "alucinaciones" in last_msg.content:
            return "agent"

        # Tras validar alucinaciones, verificamos si faltan tareas por completar
        return "grade_task_completion"

    async def _grade_task_completion(self, state: GraphState):
        """Verifica si el agente completó todas las tareas del plan usando el LLM como juez con contexto rico."""
        task_plan = state.get("task_plan") or []
        user_msgs = [m.content for m in state["messages"] if m.type == "human" and not str(m.content).startswith("[SISTEMA]")]
        last_user_msg = user_msgs[-1] if user_msgs else ""
        agent_msg = state["messages"][-1].content

        # Si no hay plan (query conversacional) → no hay nada que auditar
        if not task_plan:
            return {"messages": []}

        # Mapear tools ejecutadas UNICAMENTE en este turno (posteriores al último HumanMessage)
        used_tools: dict[str, str] = {}  # tool_name -> snippet
        
        # Encontrar el índice del último mensaje humano del usuario
        last_human_idx = -1
        for i, msg in enumerate(state["messages"]):
            if msg.type == "human" and not str(msg.content).startswith("[SISTEMA]"):
                last_human_idx = i
                
        # Solo recolectar herramientas que aparezcan DESPUÉS de ese mensaje
        current_turn_msgs = state["messages"][last_human_idx + 1:] if last_human_idx != -1 else state["messages"]
        
        for msg in current_turn_msgs:
            if msg.type == "tool" and msg.name not in used_tools:
                snippet = str(msg.content)[:100].replace("\n", " ")
                used_tools[msg.name] = snippet

        # --- AUDITORIA ESTRICTA: ¿El agente dijo "No encontré" sin siquiera USAR la herramienta de búsqueda? ---
        # Si el agente dice que no encontró nada pero el plan pedía búsqueda y NO hay ToolMessages en este turno...
        agent_says_not_found = "Lo siento, no pude obtener datos" in agent_msg or "La búsqueda no arrojó resultados" in agent_msg or "No encontré información" in agent_msg
        
        needed_tools = [s["tool"] for s in task_plan if s["tool"] in [_RETRIEVER_TOOL_NAME, "web_search"]]
        if agent_says_not_found and needed_tools and not any(t in used_tools for t in needed_tools):
            retries = state.get("generate_retry_count", 0)
            if retries < MAX_RETRIES:
                logger.warning(f"Auditor: El agente declinó sin intentar las herramientas planificadas ({needed_tools}). Nudge.")
                return {
                    "generate_retry_count": retries + 1,
                    "messages": [HumanMessage(content=f"[SISTEMA]: Has dicho que no encontraste información, pero el plan de ejecución indicaba usar {needed_tools} y NO las has usado en este turno. DEBES usar las herramientas correspondientes antes de rendirte.")]
                }

        # Marcar steps como completados
        for step in task_plan:
            if step["tool"] in used_tools:
                step["done"] = True

        pending_steps = [s for s in task_plan if not s["done"]]
        
        # Si todo está completado → OK
        if not pending_steps:
            return {"messages": [], "task_plan": task_plan}  # Actualizar plan con done=True

        # Hay pasos pendientes — cargar prompt del auditor desde template externo
        plan_str = "\n".join(
            [f"  [{'DONE' if s['done'] else 'PENDING'}] {s['tool']}: {s['reason']}" for s in task_plan]
        )
        tools_context = "\n".join(
            [f"  - {name} → '{snippet}'" for name, snippet in used_tools.items()]
        ) or "  Ninguna herramienta fue ejecutada."
        pending_str = ", ".join([s["tool"] for s in pending_steps])

        try:
            audit_prompt = self.prompt_loader.get_prompt(
                "grade_task_completion.jinja2",
                version=state.get("prompt_version", "rag_v3"),
                user_message=last_user_msg,
                plan_str=plan_str,
                tools_context=tools_context,
                agent_response=str(agent_msg)[:300],
                pending_str=pending_str,
            )
        except FileNotFoundError:
            # Fallback inline por si el template no existe en la versión del prompt
            audit_prompt = (
                f"El usuario pidió: {last_user_msg}\n"
                f"Plan: {plan_str}\n"
                f"Tools usadas: {tools_context}\n"
                f"Pasos pendientes: {pending_str}\n"
                "\u00bfFalta ejecutar alguno? CALIFICA 'no' y describe la herramienta faltante. Si todo está bien o no se pudo, CALIFICA 'yes'."
            )

        retries = state.get("generate_retry_count", 0)
        try:
            response = await self.checker_completion_model.ainvoke(audit_prompt)
        except Exception as e:
            logger.warning(f"Grade task completion LLM failed: {e}. Approving task.")
            return {"messages": [], "task_plan": task_plan}

        if response.binary_score == "no":
            if retries >= MAX_RETRIES:
                logger.warning(f"MAX_RETRIES ({MAX_RETRIES}) reached in grade_task_completion. Giving up.")
                return {"messages": [], "generate_retry_count": retries, "task_plan": task_plan}
            logger.info(f"Task incomplete: {response.missing_action}. Retry {retries + 1}/{MAX_RETRIES}.")
            return {
                "generate_retry_count": retries + 1,
                "task_plan": task_plan,
                "messages": [HumanMessage(content=f"[SISTEMA]: Aún no has completado la solicitud del usuario. Tarea pendiente: {response.missing_action}. DEBES usar la herramienta correspondiente AHORA MISMO.")]
            }

        return {"messages": [], "task_plan": task_plan}

    async def _grade_task_completion_router(self, state: GraphState) -> str:
        last_msg = state["messages"][-1]
        # Si el supervisor inyectó una instrucción del sistema como HumanMessage, volvemos al agente
        if isinstance(last_msg, HumanMessage) and "[SISTEMA]: Aún no has completado" in last_msg.content:
            return "agent"

        # Si todo está ok, limpiar y terminar
        return "cleanup_rag_memory"

    async def _summarize_run(self, state: GraphState):
        """Genera un resumen breve del turno actual e INMEDIATAMENTE poda mensajes intermedios."""
        # --- FIX PARA TESTS: Si no hay checkpointer, no resumimos ni borramos el historial ---
        if self.checkpointer is None:
            return {}

        messages = state["messages"]
        
        # 1. Encontrar el último mensaje real del usuario
        last_human_idx = -1
        for i, msg in enumerate(messages):
            if msg.type == "human" and not str(msg.content).startswith("[SISTEMA]"):
                last_human_idx = i
        
        if last_human_idx == -1:
            return {}

        user_input = messages[last_human_idx].content
        ai_output = messages[-1].content  # La respuesta final del agente

        # Normalizar contenido
        if isinstance(user_input, list):
            user_input = "".join(str(c) for c in user_input)
        if isinstance(ai_output, list):
            ai_output = "".join(str(c) for c in ai_output)
        
        # 2. Identificar y recolectar mensajes intermedios para el resumen y posterior borrado
        intermediate_messages = messages[last_human_idx + 1 : -1]
        intermediate_logs = []
        delete_messages = []

        for msg in intermediate_messages:
            if msg.type in ["ai", "tool"]:
                role = "Asistente (Plan)" if msg.type == "ai" else f"Herramienta ({getattr(msg, 'name', 'unknown')})"
                intermediate_logs.append(f"{role}: {str(msg.content)[:200]}")
                
            # Siempre marcamos para borrar si tiene ID (para limpiar la historia)
            if hasattr(msg, "id") and msg.id:
                delete_messages.append(RemoveMessage(id=msg.id))
        
        intermediate_str = "\n".join(intermediate_logs) if intermediate_logs else ""
        
        try:
            prompt = self.prompt_loader.get_prompt(
                "summarize_run.jinja2",
                version=state.get("prompt_version", "rag_v4"),
                user_input=user_input,
                ai_output=ai_output,
                intermediate_messages=intermediate_str
            )
            response = await self.model.ainvoke([HumanMessage(content=prompt)])
            
            # Devolvemos el nuevo resumen Y la instrucción de borrado
            return {
                "run_summaries": [response.content],
                "messages": delete_messages
            }
        except Exception as e:
            logger.warning(f"Summarize run failed: {e}")
            return {"messages": delete_messages} # Al menos intentamos limpiar la historia

    async def _summarize_conversation(self, state: GraphState):
        """
        Resume la conversación globalmente si se supera el umbral de mensajes.
        Colapsa el historial preservando el último Human input, AI output y Summarize Run.
        """
        # --- FIX PARA TESTS: Si no hay checkpointer, no resumimos ni borramos el historial ---
        if self.checkpointer is None:
            return {}

        messages = state["messages"]
        human_msgs = [m for m in messages if m.type == "human" and not str(m.content).startswith("[SISTEMA]")]
        
        # Trigger: >= 4 human messages
        if len(human_msgs) < 4:
            return {}

        # 1. Identificar mensajes a preservar (el último turno completo)
        try:
            # Ahora el resumen no está en 'messages', sino en 'run_summaries'
            run_summaries = state.get("run_summaries", [])
            last_run_summary_text = run_summaries[-1] if run_summaries else ""
            
            # Retrocedemos para buscar el par Input/Output real
            last_ai_response = None
            last_human_input = None
            
            for m in reversed(messages):
                if last_ai_response is None and m.type == "ai" and not m.tool_calls:
                    last_ai_response = m
                elif last_human_input is None and m.type == "human" and not str(m.content).startswith("[SISTEMA]"):
                    last_human_input = m
                
                if last_ai_response and last_human_input:
                    break
            
            if not last_ai_response or not last_human_input:
                logger.warning("No se pudo identificar el par Input/Output para preservar. Abortando summarization.")
                return {}

            preserved_ids = {last_ai_response.id, last_human_input.id}
            history_to_collapse = [m for m in messages if m.id not in preserved_ids]
            
            # Agregar los resúmenes de corridas previas al historial a colapsar si queremos que el global los incluya
            run_summaries_str = "\n".join([f"Turno: {s}" for s in run_summaries])
            
            # 2. Generar el nuevo resumen consolidado
            history_str = "\n".join([f"{m.type}: {m.content}" for m in history_to_collapse])
            history_str += f"\n\nResúmenes de turnos recientes:\n{run_summaries_str}"
            
            previous_summary = state.get("summary", "")

            prompt = self.prompt_loader.get_prompt(
                "summarize_global.jinja2",
                version=state.get("prompt_version", "rag_v4"),
                previous_summary=previous_summary,
                history_str=history_str
            )
            
            response = await self.model.ainvoke([HumanMessage(content=prompt)])
            
            # Borramos los mensajes colapsados y RESETEAMOS la lista de summaries locales
            # ya que ahora están incorporados en el resumen global.
            return {
                "summary": response.content,
                "messages": [RemoveMessage(id=m.id) for m in history_to_collapse],
                "run_summaries": None # Resetea la lista usando el reductor custom
            }

        except Exception as e:
            logger.warning(f"Global summarization failed: {e}")
            return {}

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
        
        tags = ["agent_generation"]
        metadata = {}
        
        if user_info and user_info.get("is_stress_test"):
            tags.append("stress_test_v1")
            metadata["test_type"] = "load_test"

        config = {
            "configurable": {
                "thread_id": thread_id,
                "user_id": user_id,
            },
            "tags": tags,
            "metadata": metadata,
        }

        input_message = {
            "messages": [("user", message)],
            "user_info": user_info,
            "prompt_version": prompt_version,
            "retrieve_retry_count": 0,
            "generate_retry_count": 0,
            "docs_parse_retries": 0,
            "hallucinations_parse_retries": 0,
            "task_plan": None,
        }

        return await self.graph.ainvoke(input_message, config=config)


    async def astream_chat(self, message: str, thread_id: str, user_info: dict, prompt_version: str):
        """
        Versión streaming del chat. Emite eventos detallados del grafo usando astream_events.
        """
        user_id = user_info.get("user_id") if user_info else None
        
        tags = ["agent_generation"]
        metadata = {}
        
        if user_info and user_info.get("is_stress_test"):
            tags.append("stress_test_v1")
            metadata["test_type"] = "load_test"

        config = {
            "configurable": {
                "thread_id": thread_id,
                "user_id": user_id,
            },
            "tags": tags,
            "metadata": metadata,
        }

        input_message = {
            "messages": [("user", message)],
            "user_info": user_info,
            "prompt_version": prompt_version,
            "retrieve_retry_count": 0,
            "generate_retry_count": 0,
            "docs_parse_retries": 0,
            "hallucinations_parse_retries": 0,
            "task_plan": None,
        }

        # version="v2" es el estándar actual recomendado por LangChain para eventos
        async for event in self.graph.astream_events(input_message, config=config, version="v2"):
            yield event