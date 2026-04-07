from src.tools.weather import get_weather_tool
from src.tools.metadata_filter import knowledge_base_retriever
from src.tools.web_search import web_search
from src.tools.save_note import save_note_to_knowledge_base
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
                                     de fecha (date_from), fuente (source_filter)
                                     y tipo de doc. El user_id se inyecta vía
                                     RunnableConfig (invisible para el LLM).
        - web_search               → búsqueda en internet vía DuckDuckGo.
                                     Solo usar si la base local no tiene respuesta
                                     o si el usuario lo pide explícitamente.
        - save_note_to_knowledge_base → guarda notas/resúmenes en la base de
                                     conocimientos vía Kafka (fire-and-forget).
        - get_weather              → clima actual (si la API key está configurada).
        """
        tools = [knowledge_base_retriever, web_search, save_note_to_knowledge_base]

        weather_tool = get_weather_tool()
        if weather_tool:
            tools.append(weather_tool)

        return tools
