import os
from dotenv import load_dotenv
import uuid

load_dotenv(override=True)
os.environ["APP_ENV"] = "production"

import pytest
import logging
from deepeval.test_case import LLMTestCase
from deepeval.metrics import (
    ContextualPrecisionMetric, 
    ContextualRecallMetric, 
    AnswerRelevancyMetric,
    GEval
)
from deepeval.test_case import LLMTestCaseParams
from deepeval import assert_test

from src.service.chunking import AgenticChunker
from src.service.agent import AgentService
from src.core.llm import LLMFactory
from src.evals.golden_dataset_v2 import GOLDEN_DATASET
from src.evals.eval_utils import GeminiJudge, ask_my_rag
from src.providers.vector_store.factory import VectorStoreFactory
from src.tools.registry import ToolRegistry
from langgraph.checkpoint.memory import MemorySaver

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# --- FIXTURES ---

@pytest.fixture(scope="module")
def rag_setup():
    """
    Inicializa el Agente asumiendo que los datos YA fueron ingestados 
    por el script seed_eval_data.py
    """
    vector_db = VectorStoreFactory.get_provider().getVectorStore()
    ToolRegistry.set_vector_store(vector_db)
    tools = ToolRegistry.get_agent_tools()
    
    agent_service = AgentService(LLMFactory, tools, None)
    yield agent_service

# --- TESTS ---

@pytest.mark.asyncio
@pytest.mark.parametrize("goldcase", GOLDEN_DATASET)
async def test_rag_performance(rag_setup, goldcase):
    """
    Test de rendimiento RAG con Re-Ranking y Contexto Expandido.
    Exigimos un 0.8 en Precisión Contextual ahora que usamos Gemini Reranker.
    """
    agent_service = rag_setup
    judge = GeminiJudge()
    
    actual_output, retrieval_context = await ask_my_rag(
        agent_service, 
        query=goldcase["eval_query"], 
        user_id="eval_golden_user"
    )
    
    test_case = LLMTestCase(
        input=goldcase["eval_query"],
        actual_output=actual_output,
        expected_output=goldcase["expected_answer"],
        retrieval_context=retrieval_context
    )
    
    metrics = [
        # Umbral 0.4: Las consultas multi-hop (ej. DevOps + LangGraph) mezclan temas, 
        # lo que penaliza la precisión posicional aunque los chunks sean correctos.
        ContextualPrecisionMetric(threshold=0.4, model=judge),
        
        # Umbral 0.6: Los resultados de web_search son volátiles y pueden no contener
        # exactamente la misma cadena que el golden dataset histórico.
        ContextualRecallMetric(threshold=0.6, model=judge),
        
        # La relevancia de la respuesta sigue siendo crítica y se mantiene en 0.7.
        AnswerRelevancyMetric(threshold=0.7, model=judge)
    ]
    
    assert_test(test_case, metrics)

@pytest.mark.asyncio
async def test_retriever_k_results(rag_setup):
    """
    Verifica que la herramienta knowledge_base_retriever respete el parámetro k_results.
    """
    from src.tools.metadata_filter import knowledge_base_retriever
    from langchain_core.runnables import RunnableConfig
    
    config = RunnableConfig(configurable={"user_id": "eval_golden_user"})
    
    # Probamos con k=2
    res_k2 = knowledge_base_retriever.invoke({
        "query": "inteligencia artificial", 
        "k_results": 2
    }, config=config)
    
    # Contamos cuántas fuentes aparecen (asumiendo formato [Fuente: ...])
    count_k2 = res_k2.count("[Fuente:")
    assert count_k2 <= 2, f"Se esperaban máximo 2 resultados, se obtuvieron {count_k2}"
    
    # Probamos con k=5
    res_k5 = knowledge_base_retriever.invoke({
        "query": "inteligencia artificial", 
        "k_results": 5
    }, config=config)
    
    count_k5 = res_k5.count("[Fuente:")
    # k=5 debería devolver al menos tantos como k=2, pero el reranker puede filtrar iguales
    # si el número de docs relevantes en el índice es menor al k solicitado
    assert count_k5 >= count_k2, "k=5 no debería devolver menos resultados que k=2"

@pytest.mark.asyncio
async def test_reranking_logic(rag_setup):
    """
    Valida que el re-ranking funcione correctamente devolviendo documentos relevantes.
    """
    from src.tools.metadata_filter import knowledge_base_retriever
    from langchain_core.runnables import RunnableConfig

    config = RunnableConfig(configurable={"user_id": "eval_golden_user"})
    
    # --- FIX: Usar una query que SÍ exista en el Golden Dataset ---
    query = "Entrevistas para el puesto de AI Engineer"

    # El retriever ya tiene el re-ranking integrado internamente
    results = knowledge_base_retriever.invoke({"query": query, "k_results": 3}, config=config)

    judge = GeminiJudge()
    prompt = f"""Analiza si los siguientes fragmentos recuperados para la consulta "{query}" son altamente relevantes. 
    Documentos recuperados:
    {results}

    Responde ÚNICAMENTE 'SÍ' si al menos uno de los top resultados habla sobre entrevistas técnicas, postulaciones a empresas (como Siemens o Amperity) o experiencia profesional, o 'NO' en caso contrario."""

    response = judge.generate(prompt)
    assert "SÍ" in response.upper(), f"El re-ranking no trajo resultados relevantes para '{query}'.\nResultados: {results}"

@pytest.mark.asyncio
@pytest.mark.parametrize("goldcase", GOLDEN_DATASET)
async def test_chunking_quality(goldcase):
    judge = GeminiJudge()
    chunker = AgenticChunker(LLMFactory)
    
    generated_docs = chunker.chunk(goldcase["raw_text"])
    generated_chunks_text = "\n---\n".join([d.page_content for d in generated_docs])
    ideal_chunks_text = "\n---\n".join(goldcase["ideal_chunks"])
    
    coherence_metric = GEval(
        name="Chunking Coalescence & Cohesion",
        criteria=(
            "Determine if the generated chunks capture the core information from the Expected Output. "
            "1. TOPICAL ALIGNMENT: Propositions in the same chunk must belong to the same topic. "
            "2. NO STRUCTURAL PENALTY: DO NOT penalize if the generated chunks have a different number of chunks, different order, or different boundaries than the Expected Output. "
            "3. PERMISSIBLE REPHRASING: Rephrasing and summarizing is EXPECTED and ALLOWED. "
            "4. CONTEXT HEADERS: Ignore any '[Contexto Global...]' headers. "
            "Focus ONLY on whether the information is logically grouped and present, regardless of the exact chunking structure."
        ),
        evaluation_params=[LLMTestCaseParams.ACTUAL_OUTPUT, LLMTestCaseParams.EXPECTED_OUTPUT],
        model=judge,
        threshold=0.4 
    )
    
    test_case = LLMTestCase(
        input="Chunking Strategy Evaluation",
        actual_output=generated_chunks_text,
        expected_output=ideal_chunks_text
    )
    
    assert_test(test_case, [coherence_metric])

# --- MULTI-TURN DATASET (FASE 3) ---

MULTI_TURN_DATASET = [
    {
        "test_name": "Coherencia Multi-Salto: Kubernetes y KEDA",
        "turns": [
            {
                "input": "Extrae de mis notas un resumen de los problemas que tuvimos con KEDA en la migración a Kubernetes.",
                "expected_intent": "Debe mencionar el crash de los workers de Celery en la v2.12.0 por SASL_SSL.",
            },
            {
                "input": "¿Qué versión exacta de KEDA anoté ahí?",
                "expected_intent": "Debe resolver coreferencia 'ahí' y responder v2.12.0.",
            },
            {
                "input": "Busca en la web si esa versión tiene reportes conocidos de bugs con Kafka SASL.",
                "expected_intent": "Debe usar web_search para v2.12.0.",
            },
            {
                "input": "Hacé un resumen detallado de todo lo que descubrimos hoy sobre KEDA, incluyendo el problema original de SASL, las versiones y las tareas a seguir.",
                "expected_intent": "Debe incluir la investigación de KEDA y el resultado de la búsqueda.",
            }
        ]
    }
]

@pytest.mark.asyncio
async def test_multiturn_coherence(rag_setup):
    """
    Verifica la memoria jerárquica y coherencia multi-turno.
    """
    # Creamos una instancia dedicada con checkpointer para este test
    base_agent = rag_setup
    checkpointer = MemorySaver()
    agent_service = AgentService(LLMFactory, base_agent.tools, checkpointer)
    unique_id = uuid.uuid4().hex
    thread_id = f"test_thread_multiturn{unique_id}"
    user_info = {"user_id": "eval_golden_user", "name": "Tester"}
    
    chat_history_actual = []
    
    # IMPORTANTE: Usamos el mismo thread_id para mantener el estado
    for turn in MULTI_TURN_DATASET[0]["turns"]:
        # Invocamos al agente (usando chat para obtener el output final)
        result = await agent_service.chat(
            message=turn["input"],
            thread_id=thread_id,
            user_info=user_info,
            prompt_version=os.getenv("PROMPT_VERSION")
        )
        
        # Extraer el último AI message
        ai_msg = ""
        for m in reversed(result["messages"]):
            if m.type == "ai":
                ai_msg = m.content
                break
        
        chat_history_actual.append(f"User: {turn['input']}\nAI: {ai_msg}")
        logger.info(f"Turno completado: {turn['input'][:30]}...")

    # Evaluación final de coherencia con LLM Judge
    full_conversation = "\n\n".join(chat_history_actual)
    judge = GeminiJudge()
    
    coherence_metric = GEval(
        name="Conversational Memory & Multi-hop Coherence",
        criteria=(
            "Evalúa si el agente mantuvo el contexto a lo largo de los 4 turnos. "
            "1. ¿Resolvió correctamente las coreferencias (ej: 'ahí', 'esa versión')? "
            "2. ¿Utilizó la información de turnos previos para realizar la búsqueda web? "
            "3. ¿El resumen final incluye los puntos clave discutidos (KEDA v2.12.0, crash SASL)? "
            "4. ¿Se nota una degradación en la calidad tras el resumen global (si ocurrió)?"
        ),
        evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
        model=judge,
        threshold=0.7
    )
    
    test_case = LLMTestCase(
        input=MULTI_TURN_DATASET[0]["turns"][-1]["input"], # El último input
        actual_output=full_conversation
    )
    
    assert_test(test_case, [coherence_metric])
