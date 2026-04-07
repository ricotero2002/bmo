import os
from typing import Optional, Type
from pydantic import BaseModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_core.language_models.chat_models import BaseChatModel

class LLMFactory:
    """Fábrica de modelos de lenguaje (LLMFactory) con políticas nativas de Langchain (Retry y Fallback)."""
    
    @classmethod
    def create(cls, tools = None, response_format: Optional[Type[BaseModel]] = None) -> BaseChatModel:
        from src.core.telemetry import TelemetryCallbackHandler
        callbacks = [TelemetryCallbackHandler()]
        
        gemini_api_key = os.getenv("GOOGLE_API_KEY", "")
        openai_api_key = os.getenv("OPENAI_API_KEY", "")

        # 1. Definimos modelos
        try:
            primary_model = ChatGoogleGenerativeAI(
                model="gemini-2.5-flash-lite",
                temperature=0,
                google_api_key=gemini_api_key,
                callbacks=callbacks
            )
        except Exception:
            # Fallback seguro en caso de que la clave de gemini esté vacía
            primary_model = ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0,
                openai_api_key=openai_api_key,
                stream_options={"include_usage": True},
                callbacks=callbacks
            )
        '''
        fallback_model = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0,
            openai_api_key=openai_api_key,
            callbacks=callbacks
        )
        '''
        fallback_model = ChatOpenAI(
            model="gemini-2.5-flash",
            temperature=0,
            openai_api_key=gemini_api_key,
            stream_options={"include_usage": True},
            callbacks=callbacks
        )
        fallback_model2 = ChatOpenAI(
            model="gemma-3-1b-it",
            temperature=0,
            openai_api_key=gemini_api_key,
            stream_options={"include_usage": True},
            callbacks=callbacks
        )
        fallback_model3 = ChatOpenAI(
            model="gemini-1.5-pro",
            temperature=0,
            openai_api_key=gemini_api_key,
            stream_options={"include_usage": True},
            callbacks=callbacks
        )

        # 3. Aplicar tools y structured output a TODOS los modelos (principal y fallbacks)
        models = [primary_model, fallback_model, fallback_model2, fallback_model3]
        
        if tools is not None:
            models = [m.bind_tools(tools) for m in models]

        if response_format:
            models = [m.with_structured_output(response_format) for m in models]

        primary_bound = models[0]
        fallbacks_bound = models[1:]
        
        # 4. Configurar Fallbacks y Retries Nativos
        model_with_fallbacks = primary_bound.with_fallbacks(
            fallbacks_bound
        ).with_retry(
            stop_after_attempt=3,
            wait_exponential_jitter=True
        )
            
        return model_with_fallbacks
