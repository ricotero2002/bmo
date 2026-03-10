import os
import logging
from langchain_community.tools.openweathermap.tool import OpenWeatherMapQueryRun
from langchain_community.utilities.openweathermap import OpenWeatherMapAPIWrapper

logger = logging.getLogger(__name__)

def get_weather_tool():
    """Returns the OpenWeatherMap tool if the API key is set, else None."""
    api_key = os.getenv("OPENWEATHERMAP_API_KEY")
    if not api_key:
        logger.warning("OPENWEATHERMAP_API_KEY no configurada. Herramienta del clima deshabilitada.")
        return None
        
    try:
        wrapper = OpenWeatherMapAPIWrapper(openweathermap_api_key=api_key)
        tool = OpenWeatherMapQueryRun(api_wrapper=wrapper)
        # Adaptar nombre o descripción si fuera necesario
        tool.description = "Permite obtener el clima actual para una ubicación. input debe ser de la forma 'Ciudad, Pais' ej: 'Buenos Aires, AR'"
        return tool
    except Exception as e:
        logger.error(f"Error inicializando OpenWeatherMap tool: {e}")
        return None
