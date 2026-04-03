import os
from dotenv import load_dotenv

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
        ContextualPrecisionMetric(threshold=0.8, model=judge), # Incrementado de 0.5 a 0.8
        ContextualRecallMetric(threshold=0.7, model=judge),
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
    assert count_k5 > count_k2, "k=5 debería devolver más resultados que k=2 si hay datos suficientes"

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
            "Determine if the chunks are logically grouped and conceptually cohesive based on the Expected Output. "
            "1. TOPICAL ALIGNMENT: Propositions in the same chunk must belong to the same specific sub-topic. "
            "2. LIST PRESERVATION: Lists of tasks, companies, or related items should ideally be grouped together if they share a context, but minor restructuring is acceptable. "
            "3. PERMISSIBLE REPHRASING: The generated chunks WILL rephrase, decontextualize, and summarize the raw text. This is EXPECTED and ALLOWED as long as the core meaning is not lost. "
            "4. CONTEXT HEADERS: The generated chunks may include '[Contexto Global...]' headers. Ignore these headers when evaluating cohesion. "
            "Focus on whether the Core Information from the Expected Output is present and logically grouped, not on exact string or word matching."
        ),
        evaluation_params=[LLMTestCaseParams.ACTUAL_OUTPUT, LLMTestCaseParams.EXPECTED_OUTPUT],
        model=judge,
        threshold=0.7 
    )
    
    test_case = LLMTestCase(
        input="Chunking Strategy Evaluation",
        actual_output=generated_chunks_text,
        expected_output=ideal_chunks_text
    )
    
    assert_test(test_case, [coherence_metric])
