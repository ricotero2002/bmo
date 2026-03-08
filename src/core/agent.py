import os
from typing import Optional, Type
from pydantic import BaseModel
from langchain.agents import create_agent
from langchain.agents.middleware.model_fallback import ModelFallbackMiddleware
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain.agents.structured_output import ProviderStrategy

class AgentFactory:
    """Fábrica de agentes configurada con políticas nativas de Langchain (Retry y Fallback)."""
    
    @classmethod
    def create(cls, response_format: Optional[Type[BaseModel]] = None):
        gemini_api_key = os.getenv("GOOGLE_API_KEY", "")
        openai_api_key = os.getenv("OPENAI_API_KEY", "")

        # 1. Definimos modelos
        try:
            primary_model = ChatGoogleGenerativeAI(
                model="gemini-2.5-flash-lite",
                temperature=0,
                google_api_key=gemini_api_key
            )
        except Exception:
            # Fallback seguro en caso de que la clave de gemini esté vacía
            primary_model = ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0,
                openai_api_key=openai_api_key
            )
        '''
        fallback_model = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0,
            openai_api_key=openai_api_key
        )
        '''
        fallback_model = ChatOpenAI(
            model="gemini-2.5-flash",
            temperature=0,
            openai_api_key=gemini_api_key
        )
        fallback_model2 = ChatOpenAI(
            model="gemma-3-1b-it",
            temperature=0,
            openai_api_key=gemini_api_key
        )
        fallback_model3 = ChatOpenAI(
            model="gemini-1.5-pro",
            temperature=0,
            openai_api_key=gemini_api_key
        )
        

        # 2. Middleware de Fallback nativo
        fallback = ModelFallbackMiddleware(
            fallback_model,  # Try first on error
            fallback_model2,
            fallback_model3
        )

        # 3. Configuración de Salida Estructurada (Structured Output) ProviderStrategy
        kwargs = {}
        if response_format:
            kwargs["response_format"] = ProviderStrategy(response_format)

        # 4. Creamos el LangGraph Agent y aplicamos Retry sobre todo el grafo
        agent = create_agent(
            model=primary_model,
            tools=[],
            middleware=[fallback],
            **kwargs
        ).with_retry(
            stop_after_attempt=3,
            wait_exponential_jitter=True
        )
        return agent
