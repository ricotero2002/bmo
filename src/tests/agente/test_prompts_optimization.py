import pytest
import os
from src.service.prompt_loader import PromptLoader
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, LLMTestCaseParams
from src.core.llm import LLMFactory

@pytest.mark.asyncio
async def test_summarize_run_prompt():
    """Prueba aislada del prompt summarize_run con DeepEval."""
    loader = PromptLoader()
    
    user_input = "Extrae mis notas sobre los problemas de KEDA en Kubernetes."
    ai_output = "Encontré que el 05/04/2026 hubo un crash de los workers de Celery por un bug en KEDA v2.12.0 con autenticación SASL_SSL en Kafka."
    
    prompt = loader.get_prompt(
        "summarize_run.jinja2",
        version="rag_v4",
        user_input=user_input,
        ai_output=ai_output
    )
    
    # Aquí simularías la llamada al LLM con el prompt generado
    # Para el test, vamos a evaluar si el prompt contiene las variables correctas
    assert user_input in prompt
    assert ai_output in prompt
    assert "KEDA" in prompt

@pytest.mark.asyncio
async def test_summarize_global_prompt():
    """Prueba aislada del prompt summarize_global."""
    loader = PromptLoader()
    
    previous_summary = "El usuario está migrando BMO de OKE a EKS para bajar costos."
    history_str = "human: ¿Qué pasó con KEDA?\nai: Hubo un crash en la v2.12.0 por SASL_SSL."
    
    prompt = loader.get_prompt(
        "summarize_global.jinja2",
        version="rag_v4",
        previous_summary=previous_summary,
        history_str=history_str
    )
    
    assert "v2.12.0" in prompt
    assert "OKE a EKS" in prompt
    assert "Resumen Histórico Previo" in prompt

# Nota: Para ejecutar evaluaciones reales de DeepEval necesitarías configurar el modelo juez
# y hacer la llamada real al LLM. Aquí dejamos la estructura preparada.
