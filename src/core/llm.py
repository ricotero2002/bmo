from typing import Optional, Type
from pydantic import BaseModel
from langchain_openrouter import ChatOpenRouter
from langchain_core.language_models.chat_models import BaseChatModel


class LLMFactory:
    """Fábrica de modelos nativa usando OpenRouter y fallbacks de modelos free."""

    HEAVY_MODEL_NAMES = [
        "nousresearch/hermes-3-llama-3.1-405b:free",
        "meta-llama/llama-3.3-70b-instruct:free",
        "qwen/qwen3-next-80b-a3b-instruct:free",
        "openai/gpt-oss-120b:free",
        "nvidia/nemotron-3-super-120b-a12b:free",
        "google/gemma-4-31b-it:free",
        "google/gemma-4-26b-a4b-it:free",
        "qwen/qwen3-coder:free",
        "z-ai/glm-4.5-air:free",
        "openai/gpt-oss-20b:free",
        "google/gemma-3-27b-it:free",
        "nvidia/nemotron-3-nano-30b-a3b:free",
        "cognitivecomputations/dolphin-mistral-24b-venice-edition:free",
        "minimax/minimax-m2.5:free",
        "nvidia/nemotron-nano-12b-v2-vl:free",
        "nvidia/nemotron-nano-9b-v2:free",
        "meta-llama/llama-3.2-3b-instruct:free",
        "google/gemma-3-4b-it:free",
        "liquid/lfm-2.5-1.2b-instruct:free",
        "liquid/lfm-2.5-1.2b-thinking:free",
        "google/gemma-3n-e4b-it:free",
        "google/gemma-3n-e2b-it:free",
    ]

    LITE_MODEL_NAMES = [
        "meta-llama/llama-3.2-3b-instruct:free",
        "google/gemma-3-4b-it:free",
        "nvidia/nemotron-nano-9b-v2:free",
        "google/gemma-3n-e4b-it:free",
        "openai/gpt-oss-20b:free",
        "liquid/lfm-2.5-1.2b-instruct:free",
        "minimax/minimax-m2.5:free",
        "google/gemma-3n-e2b-it:free",
        "google/gemma-3-27b-it:free",
        "nvidia/nemotron-3-nano-30b-a3b:free",
        "google/gemma-4-26b-a4b-it:free",
        "google/gemma-4-31b-it:free",
        "qwen/qwen3-coder:free",
        "z-ai/glm-4.5-air:free",
        "cognitivecomputations/dolphin-mistral-24b-venice-edition:free",
        "meta-llama/llama-3.3-70b-instruct:free",
        "qwen/qwen3-next-80b-a3b-instruct:free",
        "openai/gpt-oss-120b:free",
        "nvidia/nemotron-3-super-120b-a12b:free",
        "nousresearch/hermes-3-llama-3.1-405b:free",
        "nvidia/nemotron-nano-12b-v2-vl:free",
        "liquid/lfm-2.5-1.2b-thinking:free",
    ]

    PLANNER_PRIMARY = "liquid/lfm-2.5-1.2b-thinking:free"
    JUDGE_PRIMARY = "meta-llama/llama-3.3-70b-instruct:free"
    JUDGE_SECONDARY = "google/gemma-4-31b-it:free"
    CODER_PRIMARY = "qwen/qwen3-coder:free"

    @classmethod
    def _base_kwargs(cls) -> dict:
        from src.core.telemetry import TelemetryCallbackHandler

        callbacks = [TelemetryCallbackHandler()]
        return {
            "temperature": 0,
            "callbacks": callbacks,
            "model_kwargs": {"stream_options": {"include_usage": True}},
        }

    @classmethod
    def _dedupe_preserve_order(cls, model_names: list[str]) -> list[str]:
        seen = set()
        unique = []
        for name in model_names:
            if name in seen:
                continue
            seen.add(name)
            unique.append(name)
        return unique

    @classmethod
    def _build_models_from_names(cls, model_names: list[str]):
        kwargs = cls._base_kwargs()
        
        # OpenRouter ahora requiere los metadatos como headers
        headers = {
            "HTTP-Referer": "http://localhost:8000",
            "X-Title": "BMO Agent"
        }
        kwargs["default_headers"] = headers
        
        import os
        from langchain_openai import ChatOpenAI
        
        # Usamos ChatOpenAI para esquivar el bug interno de langchain_openrouter con x_title
        api_key = os.getenv("OPENROUTER_API_KEY")
        return [
            ChatOpenAI(
                model=name, 
                api_key=api_key, 
                base_url="https://openrouter.ai/api/v1", 
                **kwargs
            ) for name in model_names
        ]

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
            stop_after_attempt=5,
            wait_exponential_jitter=True
        )
            
        return model_with_fallbacks

    @classmethod
    def create(cls, tools = None, response_format: Optional[Type[BaseModel]] = None) -> BaseChatModel:
        """Modelo principal de razonamiento pesado (lista HEAVY o TOOL)."""
        # Si requiere herramientas, usamos una lista restrictiva que soporta tools nativas en OpenRouter
        if tools is not None:
            tool_models = [
                "meta-llama/llama-3.3-70b-instruct:free",
                "qwen/qwen3-coder:free",
                "google/gemma-3-27b-it:free",
                "nvidia/nemotron-nano-9b-v2:free",
                "meta-llama/llama-3.2-3b-instruct:free"
            ]
            models = cls._build_models_from_names(tool_models)
        else:
            models = cls._build_models_from_names(cls.HEAVY_MODEL_NAMES)
            
        return cls._bind_and_fallback(models, tools, response_format)

    @classmethod
    def create_lite(cls, tools = None, response_format: Optional[Type[BaseModel]] = None) -> BaseChatModel:
        """Modelo rápido para resumen, extracción y clasificación liviana (lista LITE)."""
        models = cls._build_models_from_names(cls.LITE_MODEL_NAMES)
        return cls._bind_and_fallback(models, tools, response_format)

    @classmethod
    def create_planner(cls, tools=None, response_format: Optional[Type[BaseModel]] = None) -> BaseChatModel:
        """Especialista de planificación, prioriza un modelo thinking."""
        model_names = cls._dedupe_preserve_order([cls.PLANNER_PRIMARY, *cls.LITE_MODEL_NAMES])
        models = cls._build_models_from_names(model_names)
        return cls._bind_and_fallback(models, tools, response_format)

    @classmethod
    def create_judge(cls, tools=None, response_format: Optional[Type[BaseModel]] = None) -> BaseChatModel:
        """Especialista de evaluación crítica (faithfulness/relevancy)."""
        model_names = cls._dedupe_preserve_order([
            cls.JUDGE_PRIMARY,
            cls.JUDGE_SECONDARY,
            *cls.HEAVY_MODEL_NAMES,
        ])
        models = cls._build_models_from_names(model_names)
        return cls._bind_and_fallback(models, tools, response_format)

    @classmethod
    def create_coder(cls, tools=None, response_format: Optional[Type[BaseModel]] = None) -> BaseChatModel:
        """Especialista en estructura/JSON para tasks de chunking agentico."""
        model_names = cls._dedupe_preserve_order([cls.CODER_PRIMARY, *cls.LITE_MODEL_NAMES])
        models = cls._build_models_from_names(model_names)
        return cls._bind_and_fallback(models, tools, response_format)
