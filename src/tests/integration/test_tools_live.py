"""
Tests de Integración "Live" — Herramientas Fase 7 Parte 3

Prueban el acceso real a internet (DuckDuckGo) sin mocks.
Uso: pytest src/tests/integration/test_tools_live.py -v -s
"""
import pytest
import logging
from src.tools.web_search import web_search

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@pytest.mark.asyncio
async def test_web_search_live_api():
    """
    Prueba real de web_search contra los servidores de DuckDuckGo.
    Verifica que la respuesta no sea un mensaje de error y contenga datos reales.
    """
    query = "Últimas noticias sobre Inteligencia Artificial 2026"
    logger.info(f"Ejecutando búsqueda real DuckDuckGo para: '{query}'")
    
    # Invocamos la tool (es una @tool de LangChain, usamos .invoke)
    result = web_search.invoke({"query": query})
    
    logger.info("Resultado de la búsqueda live:")
    logger.info("-" * 40)
    logger.info(result[:1000] + "..." if len(result) > 1000 else result)
    logger.info("-" * 40)
    
    # Verificaciones básicas de una respuesta exitosa
    assert "Resultados de la Web:" in result
    assert "Título:" in result
    assert "URL:" in result
    assert "http" in result  # Debe haber links reales
    
    # Verificamos que no sea el mensaje de error genérico
    assert "Hubo un error al intentar acceder a internet" not in result
    assert "La búsqueda web no arrojó resultados útiles" not in result