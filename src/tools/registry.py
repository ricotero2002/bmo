from src.tools.weather import get_weather_tool
from src.tools.metadata_filter import knowledge_base_retriever, _vector_store
import src.tools.metadata_filter as _metadata_filter_module


class ToolRegistry:
    @staticmethod
    def set_vector_store(vector_store) -> None:
        """
        Registra el vector store a nivel de módulo para que la tool
        knowledge_base_retriever pueda acceder a él en tiempo de ejecución.
        Debe llamarse una sola vez al iniciar la app (en el lifespan de FastAPI).
        """
        _metadata_filter_module._vector_store = vector_store

    @staticmethod
    def get_agent_tools():
        """
        Devuelve la lista de herramientas disponibles para el agente.

        - knowledge_base_retriever → búsqueda semántica con filtros opcionales
                                     de fecha (date_from) y fuente (source_filter).
                                     El user_id se inyecta automáticamente via
                                     RunnableConfig (invisible para el LLM).
        - get_weather              → clima actual (si la API key está configurada)
        """
        tools = [knowledge_base_retriever]

        weather_tool = get_weather_tool()
        if weather_tool:
            tools.append(weather_tool)

        return tools
