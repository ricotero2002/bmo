import logging
from typing import Literal
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage, RemoveMessage
from langgraph.graph import StateGraph, START, END
from langgraph.types import RetryPolicy, Command
from langgraph.prebuilt import ToolNode

from src.schemas.graph_state import GraphState, GradeDocuments, GradeHallucinations
from src.service.prompt_loader import PromptLoader
from langchain_core.prompts import PromptTemplate

logger = logging.getLogger(__name__)

MAX_RETRIES = 2

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
        
        # Routing condicional para el agente
        workflow.add_conditional_edges("agent", self._agent_router)
        
        # Routing para el finalizador de tools
        workflow.add_conditional_edges("tools", self._tools_router)
        
        # Routing finalizador de documentos evaluados
        workflow.add_conditional_edges("grade_documents", self._grade_docs_router)
        
        # Routing finalizador de la verificación de alucinaciones
        workflow.add_conditional_edges("grade_hallucinations", self._grade_hallucinations_router)
        
        # Reescribir query va de nuevo al agente
        workflow.add_edge("rewrite_query", "agent")
        
        return workflow.compile(checkpointer=self.checkpointer)
    
    async def _call_agent(self, state: GraphState):
        prompt_template = PromptLoader.load(state.get("prompt_version", "rag_v1"))
        chain = prompt_template | self.model
        
        user_info = state.get("user_info") or {"name": "Usuario"}
        
        response = await chain.ainvoke({
            "user_name": user_info.get("name", "Usuario"),
            "messages": state["messages"]
        })
        
        return {"messages": [response], "generated": response}

    def _agent_router(self, state: GraphState) -> str:
        messages = state["messages"]
        last_message = messages[-1]
        
        # Si la LLM decidió llamar a una herramienta
        if last_message.tool_calls:
            return "tools"
            
        # Si NO llamó a herramientas, verificamos si en todo este turno se usó el retriever.
        # Solo revisamos los mensajes desde la última pregunta del usuario.
        # Si no llamo a ninguna tool es una respuesta, si es retriver chequeo validez
        retriever_used = False
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                break
            if isinstance(msg, ToolMessage) and msg.name == "knowledge_base_retriever":
                retriever_used = True
                break
                
        if retriever_used:
            return "grade_hallucinations"
            
        # Si la conversación es muy larga, la resumimos
        if len(messages) > 6:
            return "summarize_conversation"
            
        return END

    def _tools_router(self, state: GraphState) -> str:
        messages = state["messages"]
        last_message = messages[-1]
        
        # Usamos grade_documents solo con el RAG Retriever
        if getattr(last_message, "name", "") == "knowledge_base_retriever":
            return "grade_documents"
        
        # Si es el clima u otra tool, volvemos a intentar que conteste u opere
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
        
        # Estructuramos la LLM para Output binario
        grader_model = self.grader_docs_model
        
        prompt = PromptLoader.load(state.get("prompt_version", "rag_v1"), "grader_document.jinja2")
        # Custom prompt without system explicitly, handled manually or loaded.
        # Since PromptLoader loads standard ChatPromptTemplate with MessagesPlaceholder, we can format:
        # Actually PromptLoader expects messages placeholder but grader_document is just raw text.
        # It's safer to load the raw file.
        import os
        base_dir = os.path.dirname(os.path.dirname(__file__))
        path = os.path.join(base_dir, "core", "prompts", state.get("prompt_version", "rag_v1"), "grader_document.jinja2")
        with open(path, "r", encoding="utf-8") as f:
            template_text = f.read()
            
        pt = PromptTemplate.from_template(template_text, template_format="jinja2")
        chain = pt | grader_model
        
        try:
            res = await chain.ainvoke({"document_context": docs_text, "question": question})
            # Si tiene exito, reseteamos contador por las dudas (aunque no debería importar)
            parse_retries = 0 
        except Exception as e:
            parse_retries = state.get("docs_parse_retries", 0) + 1
            if parse_retries > MAX_RETRIES:
                logger.error(f"GradeDocuments exceeded max parsing retries. Aborting check.")
                # Si fallamos demasiadas veces intentando validar JSON, simplemente pasamos al generador
                # Asumimos que los documentos "sirven" para no trabar el sistema o lanzamos a re-escribir query.
                return {
                    "retrieve_retry_count": state.get("retrieve_retry_count", 0), 
                    "docs_parse_retries": parse_retries
                }
            
            # Error de formato/parso. Instruimos al LLM a reintentar este paso usando Command para auto-loop
            error_msg = f"Tu evaluación falló con el error: {str(e)}. Debes devolver obligatoriamente un JSON estructurado con la llave 'binary_score' con valor 'yes' o 'no'."
            logger.warning(f"GradeDocuments failed parsing (attempt {parse_retries}). Retrying.")
            return Command(
                goto="grade_documents",
                update={
                    "messages": [SystemMessage(content=error_msg)],
                    "docs_parse_retries": parse_retries
                }
            )
        
        # Si logra ejecutarse, reseteamos el loop tracker y avanzamos la lógica
        update_state = {"docs_parse_retries": 0}
        
        if res.binary_score.lower() == "yes":
            update_state["retrieve_retry_count"] = state.get("retrieve_retry_count", 0)
        else:
            update_state["retrieve_retry_count"] = state.get("retrieve_retry_count", 0) + 1
            
        return update_state

    def _grade_docs_router(self, state: GraphState) -> str:
        if state.get("retrieve_retry_count", 0) > 0 and state.get("retrieve_retry_count", 0) < MAX_RETRIES:
            # First failure -> retry query
            return "rewrite_query"
        # Otherwise, pass to agent. If valid, agent will answer. If out of retries, agent will answer with what it has.
        return "agent"

    async def _rewrite_query(self, state: GraphState):
        """Si el documento no sirve, enviamos un mensaje a la historia obligando al LLM a reintentar."""
        feedback = HumanMessage(content="Las búsquedas previas no arrojaron información relevante. Modifica tu razonamiento o parámetros de búsqueda y vuelve a intentar usar la herramienta `knowledge_base_retriever` con palabras claves diferentes.")
        return {"messages": [feedback]}

    async def _grade_hallucinations(self, state: GraphState):
        """Comprueba si la respuesta introdujo datos falsos no presentes en el documento."""
        messages = state["messages"]
        
        # Encontrar docs (útlimo ToolMessage de retriever)
        docs_text = ""
        for msg in reversed(messages):
            if isinstance(msg, ToolMessage) and msg.name == "knowledge_base_retriever":
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
                # Fallback: Si no podemos evaluarlo despues de 2 intentos, lo dejamos pasar.
                return {
                    "generate_retry_count": state.get("generate_retry_count", 0),
                    "hallucinations_parse_retries": parse_retries
                }
                
            # Error de formato/parseo. Instruimos al LLM a reintentar el evaluador
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
                feedback = HumanMessage(content="La respuesta generada contenía alucinaciones o datos que no estaban en los documentos. Vuelve a redactarla basándote ESTRICTAMENTE en los resultados de la búsqueda.")
                update_state["messages"] = [feedback]
            else:
                feedback = AIMessage(content="Lo siento, no pude obtener datos confiables de mi base de conocimientos para responder con total seguridad a esa pregunta.")
                update_state["messages"] = [feedback]
                update_state["generated"] = feedback
                
        return update_state

    def _grade_hallucinations_router(self, state: GraphState) -> str:
        count = state.get("generate_retry_count", 0)
        # We check the last message. If it was our artificial HumanMessage, we must route back to Agent.
        last_msg = state["messages"][-1]
        if isinstance(last_msg, HumanMessage) and "alucinaciones" in last_msg.content:
             return "agent"
             
        # Si la conversación es muy larga, la resumimos antes de terminar
        if len(state["messages"]) > 6:
             return "summarize_conversation"
             
        return END

    async def _summarize_conversation(self, state: GraphState):
        """Resume los mensajes anteriores de la conversación para no exceder los límites de tokens."""
        summary = state.get("summary", "")
        # Tomar todos los mensajes excepto el resumen existente y el último intercambio (últimos 2 mensajes)
        # Asumiendo que los últimos dos son Human/AI (o Human/Tool/AI combinados, por seguridad dejamos los últimos 2).
        messages = state["messages"]
        if len(messages) <= 6:
            return {"messages": []} # No-op por si acaso
            
        # El modelo condensará todo
        summary_message = (
            f"This is summary of conversation to date: {summary}\n\n"
            "Extend the summary by taking into account the new messages above."
        )
        
        # Filtramos para enviar contexto a resumir al LLM. Omitimos el último turno.
        messages_to_summarize = messages[:-2]
        
        response = await self.model.ainvoke(
            messages_to_summarize + [HumanMessage(content=summary_message)]
        )
        
        # Le decimos a LangGraph que quite los mensajes viejos, manteniendo solo los últimos 2 
        # y añadiendo el nuevo summary como SystemMessage inicial.
        delete_messages = [RemoveMessage(id=m.id) for m in messages_to_summarize]
        
        new_system_summary = SystemMessage(content=f"Resumen de la conversación hasta ahora: {response.content}")
        
        # El retorno actualiza el estado agregando las operaciones RemoveMessage 
        # y luego insertando el nuevo mensaje de sistema.
        return {
            "summary": response.content, 
            "messages": delete_messages + [new_system_summary]
        }

    async def chat(self, message: str, thread_id: str, user_info: dict, prompt_version: str):
        config = {"configurable": {"thread_id": thread_id}}
        
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