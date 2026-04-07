import logging
import requests
import json
from bs4 import BeautifulSoup
from langchain_core.tools import tool
from langchain_community.utilities import DuckDuckGoSearchAPIWrapper
from langchain_community.tools import DuckDuckGoSearchResults

logger = logging.getLogger(__name__)

def _scrape_webpage(url: str) -> str:
    """Visita una URL, extrae el HTML y devuelve el texto de los párrafos principales."""
    try:
        # Simulamos ser un navegador real para que las páginas no nos bloqueen (Error 403)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        # Timeout corto de 5 segundos para que el agente no se quede trabado si la web es lenta
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        
        # Parseamos el HTML
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extraemos solo los párrafos (<p>) para evitar leer menús, scripts o código basura
        paragraphs = soup.find_all('p')
        text_content = " ".join([p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)])
        
        # Si la página está vacía o bloqueada por JS, devolvemos string vacío
        if not text_content:
            return ""
            
        # Límite incrementado a 3000 caracteres por instrucción del usuario
        return text_content[:4000] 
        
    except Exception as e:
        logger.warning(f"No se pudo leer la URL {url}: {e}")
        return ""

@tool
def web_search(query: str) -> str:
    """
    Busca información profunda en internet. 
    ÚSALA SOLO si la base de conocimientos no tiene la respuesta,
    o si el usuario pide explícitamente buscar en la web o noticias actuales.
    """
    logger.info(f"Ejecutando búsqueda profunda web para: '{query}'")
    try:
        wrapper = DuckDuckGoSearchAPIWrapper(region="es-es", max_results=4)
        search = DuckDuckGoSearchResults(api_wrapper=wrapper, output_format="list")
        
        results_list = search.invoke(query)

        if not results_list or not isinstance(results_list, list):
            return "La búsqueda web no arrojó resultados útiles."

        cleaned_results = []
        
        # Iteramos sobre los resultados. Vamos a hacer Scraping profundo solo de los primeros 2 
        # para que sea rápido. Para el resto, usamos el snippet normal.
        for i, item in enumerate(results_list):
            if isinstance(item, dict):
                title = item.get("title", "Sin título")
                link = item.get("link", "#")
                
                # --- Deep Search: Scraping profundo de los primeros 2 resultados ---
                if i < 2 and link != "#":
                    logger.info(f"Raspando contenido real de: {link}")
                    page_content = _scrape_webpage(link)
                    
                    if page_content:
                        # Logramos leer la página completa
                        content = f"[CONTENIDO EXTRAÍDO DE LA PÁGINA]: {page_content}..."
                    else:
                        # Fallback al snippet si la página nos bloqueó o dio error
                        snippet = item.get("snippet", "")[:800]
                        content = f"[SNIPPET RESUMEN]: {snippet}..."
                else:
                    # Para los links 3 y 4, solo devolvemos el snippet para ahorrar tiempo
                    snippet = item.get("snippet", "")[:800]
                    content = f"[SNIPPET RESUMEN]: {snippet}..."
                
                cleaned_results.append(
                    f"- Título: {title}\n  URL: {link}\n  Contenido: {content}"
                )

        if not cleaned_results:
            return "La búsqueda web no arrojó resultados útiles."

        return "Resultados de la Búsqueda Profunda Web:\n\n" + "\n\n".join(cleaned_results)

    except Exception as e:
        logger.error(f"Error en web_search: {e}")
        return "Hubo un error interno al intentar acceder a internet."
