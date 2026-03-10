from langchain_core.tools.retriever import create_retriever_tool
from src.tools.weather import get_weather_tool

class ToolRegistry:
    @staticmethod
    def get_agent_tools(vector_store_retriever):
        """Devuelve la lista de herramientas disponibles para el agente."""
        tools = [
            create_retriever_tool(
                vector_store_retriever,
                "knowledge_base_retriever",
                "Busca y recupera información relevante de los documentos y el conocimiento personal del usuario."
            )
        ]
        
        # Agregamos la herramienta del clima si está disponible
        weather_tool = get_weather_tool()
        if weather_tool:
            tools.append(weather_tool)
            
        return tools
