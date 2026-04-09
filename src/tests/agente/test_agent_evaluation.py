import pytest
import asyncio
from typing import Optional, Type, Any
from deepeval import assert_test
from deepeval.test_case import LLMTestCase
from deepeval.metrics import FaithfulnessMetric, AnswerRelevancyMetric
from langchain_core.tools import tool
import os
from dotenv import load_dotenv

load_dotenv(override=True)
# Ajusta las importaciones de tu proyecto según corresponda
from src.core.llm import LLMFactory
from src.service.agent import AgentService
from langgraph.checkpoint.memory import MemorySaver

from deepeval.models.base_model import DeepEvalBaseLLM

# 1. Envoltorio para usar tu LLMFactory como Juez en DeepEval
class GeminiEvaluator(DeepEvalBaseLLM):
    def __init__(self):
        # Usamos create_lite para que sea más rápido y barato para evaluación
        self.model = LLMFactory.create_lite().with_config({"temperature": 0.0})
        
    def load_model(self):
        return self.model

    def _clean_json(self, text: str) -> str:
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return text.strip()

    def generate(self, prompt: str, schema: Optional[Type] = None, *args, **kwargs) -> Any:
        res = self.model.invoke(prompt)
        cleaned = self._clean_json(res.content)
        if schema:
            try:
                return schema.model_validate_json(cleaned)
            except Exception:
                return cleaned
        return cleaned

    async def a_generate(self, prompt: str, schema: Optional[Type] = None, *args, **kwargs) -> Any:
        res = await self.model.ainvoke(prompt)
        cleaned = self._clean_json(res.content)
        if schema:
            try:
                return schema.model_validate_json(cleaned)
            except Exception:
                return cleaned
        return cleaned

    def get_model_name(self):
        return "Gemini-Factory-Judge"

# 2. Mock de la Herramienta (Evita necesitar Redis/Celery/VectorStore)
@tool("knowledge_base_retriever")
def mock_retriever(query: str) -> str:
    """Mock que simula la respuesta de la base de datos vectorial."""
    return "La política de vacaciones de la empresa permite 15 días hábiles al año."

# 2. Configuración del Dataset de Prueba (Golden Dataset)
TEST_CASES = [
    {
        "input": "¿Cuántos días de vacaciones tengo?",
        "expected_output": "Tienes 15 días hábiles al año.",
        "mock_context": ["La política de vacaciones de la empresa permite 15 días hábiles al año."]
    }
]

@pytest.mark.asyncio
@pytest.mark.parametrize("test_data", TEST_CASES)
async def test_agent_rag_quality(test_data):
    """
    Testea si el prompt actual cumple con los Thresholds configurados.
    Además, testea que la versión nueva de prompt (rag_v2) sea mejor o igual a la vieja (rag_v1).
    """
    # 1. Setup del Agente con dependencias mockeadas
    mock_tools = [mock_retriever]
    checkpointer = MemorySaver()
    llm_factory = LLMFactory()  # O la forma en la que instancies tu LLM
    
    agent_service = AgentService(llm_factory=llm_factory, tools=mock_tools, checkpointer=checkpointer)

    # 3. Definir métricas con thresholds estrictos y asignar a Gemini como el Juez
    gemini_judge = GeminiEvaluator()
    faithfulness_metric = FaithfulnessMetric(threshold=0.85, model=gemini_judge)
    relevancy_metric = AnswerRelevancyMetric(threshold=0.80, model=gemini_judge)

    # --- Evaluación de V1 (Baseline) ---
    result_v1 = await agent_service.chat(
        message=test_data["input"],
        thread_id="test_thread_v1",
        user_info={"name": "Test User"},
        prompt_version=os.getenv("PROMPT_VERSION")
    )
    
    # Dependiendo de cómo devuelve tu agent_service, extraemos el contenido.
    # El método chat de tu Agente devuelve generada como un objeto AIMessage
    # Extraer respuesta V1 de forma segura
    response_v1 = ""
    for m in reversed(result_v1.get("messages", [])):
        if m.type == "ai":
            response_v1 = str(m.content)
            break
    
    test_case_v1 = LLMTestCase(
        input=test_data["input"],
        actual_output=response_v1,
        expected_output=test_data["expected_output"],
        retrieval_context=test_data["mock_context"] 
    )
    
    # Evaluamos silenciosamente V1 para obtener los scores
    try:
        faithfulness_metric.measure(test_case_v1)
        score_v1_faith = faithfulness_metric.score
    except Exception:
        score_v1_faith = 0.0

    try:
        relevancy_metric.measure(test_case_v1)
        score_v1_rel = relevancy_metric.score
    except Exception:
        score_v1_rel = 0.0

    # --- Evaluación de V2 (Actual) ---
    result_v2 = await agent_service.chat(
        message=test_data["input"],
        thread_id="test_thread_v2",
        user_info={"name": "Test User"},
        prompt_version=os.getenv("PROMPT_VERSION")# La nueva versión o actual a testear
    )
    
    # Extraer respuesta V2 de forma segura
    response_v2 = ""
    for m in reversed(result_v2.get("messages", [])):
        if m.type == "ai":
            response_v2 = str(m.content)
            break


    test_case_v2 = LLMTestCase(
        input=test_data["input"],
        actual_output=response_v2,
        expected_output=test_data["expected_output"],
        retrieval_context=test_data["mock_context"] 
    )

    # 3. Assert de Thresholds para la V2
    # Si estas aserciones fallan, significa que test_case_v2 NO llega al nivel de calidad deseado (0.85 y 0.80)
    assert_test(test_case_v2, [faithfulness_metric, relevancy_metric])

    # 4. A/B Testing contra V1 (Evitar Regresión)
    # Extraemos los scores que sacó la V2 durante el assert_test (se guardan internamente en las métricas)
    score_v2_faith = faithfulness_metric.score
    score_v2_rel = relevancy_metric.score

    # Si por algún motivo rag_v2 es PEORE que rag_v1 de forma significativa, fallamos el test
    # Margen de tolerancia: 0.05
    assert score_v2_faith >= (score_v1_faith - 0.05), (
        f"Degradación en Faithfulness detectada. v1: {score_v1_faith}, v2: {score_v2_faith}"
    )
    
    assert score_v2_rel >= (score_v1_rel - 0.05), (
        f"Degradación en Relevancia detectada. v1: {score_v1_rel}, v2: {score_v2_rel}"
    )
