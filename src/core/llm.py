import os
from typing import Optional, Type
from pydantic import BaseModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_core.language_models.chat_models import BaseChatModel

class LLMFactory:
    """Fábrica de modelos de lenguaje (LLMFactory) con políticas nativas de Langchain (Retry y Fallback)."""

    @classmethod
    def _get_models(cls):
        from src.core.telemetry import TelemetryCallbackHandler
        callbacks = [TelemetryCallbackHandler()]
        
        gemini_api_key = os.getenv("GOOGLE_API_KEY", "")
        # Usamos la misma clave para los modelos que usamos vía OpenAI Proxy (Gemini)
        
        # --- Definición del catálogo de modelos ---
        try:
            model_flash = ChatGoogleGenerativeAI(
                model="gemini-2.5-flash",
                temperature=0,
                google_api_key=gemini_api_key,
                callbacks=callbacks
            )
        except Exception:
            # Fallback en caso de fallo crítico en el provider de Google
            model_flash = ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0,
                openai_api_key=os.getenv("OPENAI_API_KEY"),
                stream_options={"include_usage": True},
                callbacks=callbacks
            )

        model_lite = ChatOpenAI(
            model="gemini-2.5-flash-lite",
            temperature=0,
            openai_api_key=gemini_api_key,
            stream_options={"include_usage": True},
            callbacks=callbacks
        )
        
        model_flash_preview = ChatOpenAI(
            model="gemini-3-flash-preview",
            temperature=0,
            openai_api_key=gemini_api_key,
            stream_options={"include_usage": True},
            callbacks=callbacks
        )
        
        model_gemma = ChatOpenAI(
            model="gemma-3-1b-it",
            temperature=0,
            openai_api_key=gemini_api_key,
            stream_options={"include_usage": True},
            callbacks=callbacks
        )
        
        model_pro = ChatOpenAI(
            model="gemini-1.5-pro",
            temperature=0,
            openai_api_key=gemini_api_key,
            stream_options={"include_usage": True},
            callbacks=callbacks
        )
        
        return model_flash, model_lite, model_flash_preview, model_gemma, model_pro

    @classmethod
    def _bind_and_fallback(cls, models, tools, response_format):
        """Aplica herramientas, formatos estructurados y políticas de fallback a la lista de modelos proporcionada."""
        if tools is not None:
            models = [m.bind_tools(tools) for m in models]

        if response_format:
            models = [m.with_structured_output(response_format) for m in models]

        primary_bound = models[0]
        fallbacks_bound = models[1:]
        
        # Configurar Fallbacks y Retries Nativos
        model_with_fallbacks = primary_bound.with_fallbacks(
            fallbacks_bound
        ).with_retry(
            stop_after_attempt=3,
            wait_exponential_jitter=True
        )
            
        return model_with_fallbacks

    @classmethod
    def create(cls, tools = None, response_format: Optional[Type[BaseModel]] = None) -> BaseChatModel:
        """
        Crea el modelo PRINCIPAL para el agente (Pesado).
        Jerarquía: flash -> preview -> lite -> pro -> gemma
        """
        model_flash, model_lite, model_flash_preview, model_gemma, model_pro = cls._get_models()
        
        # Orden para el agente pesado
        models = [model_flash, model_flash_preview, model_lite, model_pro, model_gemma]
        
        return cls._bind_and_fallback(models, tools, response_format)

    @classmethod
    def create_lite(cls, tools = None, response_format: Optional[Type[BaseModel]] = None) -> BaseChatModel:
        """
        Crea el modelo LIGERO para grading, planificación, resumen y chunking.
        Jerarquía: lite -> flash -> preview -> gemma
        """
        model_flash, model_lite, model_flash_preview, model_gemma, _ = cls._get_models()
        
        # Orden para tareas rutinarias y estructuradas (empezamos por lite)
        models = [model_lite, model_flash, model_flash_preview, model_gemma]
        
        return cls._bind_and_fallback(models, tools, response_format)
