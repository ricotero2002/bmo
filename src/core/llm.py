from typing import Optional, Type
from pydantic import BaseModel
from langchain_openrouter import ChatOpenRouter
from langchain_ollama import ChatOllama
from langchain_core.language_models.chat_models import BaseChatModel

class LLMFactory:
    """Fábrica de modelos nativa usando NVIDIA NIM y fallbacks."""

    # NVIDIA NIM Models (Modelos pesados, gratuitos y estables)
    # SACAMOS A MISTRAL LARGE 3 de la lista principal por su bug en NIM con las Tools
    HEAVY_MODEL_NAMES = [
        "qwen/qwen3-coder-480b-a35b-instruct",
        "bytedance/seed-oss-36b-instruct",
        "meta/llama-4-maverick-17b-128e-instruct",
    ]

    # Modelos ultra-rápidos para tareas LITE
    LITE_MODEL_NAMES = [
        "meta/llama-4-maverick-17b-128e-instruct",
        "mistralai/mistral-nemotron",
        "nvidia/nemotron-mini-4b-instruct",
    ]

    # PLANNER -> Usamos Qwen3 que maneja Structured Output a la perfección
    PLANNER_PRIMARY = "qwen/qwen3-coder-480b-a35b-instruct"
    
    # JUDGES -> Mantenemos los que ya sabemos que devuelven JSON impecable
    JUDGE_PRIMARY = "abacusai/dracarys-llama-3.1-70b-instruct"
    JUDGE_SECONDARY = "meta/llama-4-maverick-17b-128e-instruct"
    
    # CODER -> Qwen3 Coder es top tier mundial y está en la capa gratuita
    CODER_PRIMARY = "qwen/qwen3-coder-480b-a35b-instruct"


    @classmethod
    def _base_kwargs(cls) -> dict:
        return {
            "temperature": 0,
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
        models = []
        
        # Prefijos conocidos del nuevo catálogo de NVIDIA NIM
        nim_prefixes = (
            "meta/", "nvidia/", "mistralai/", "google/", "deepseek-ai/", 
            "moonshotai/", "qwen/", "z.ai/", "stepfun-ai/", "bytedance/", 
            "minimaxai/", "abacus.ai/"
        )

        for name in model_names:
            if "/" not in name or name.startswith(nim_prefixes):
                # NVIDIA NIM logic
                from langchain_nvidia_ai_endpoints import ChatNVIDIA
                import os
                
                api_key = os.getenv("NVIDIA_API_KEY")
                models.append(ChatNVIDIA(
                    model=name,
                    nvidia_api_key=api_key,
                    temperature=kwargs.get("temperature", 0.0),
                    max_tokens=8192,  # Evita que el JSON se ampute y cause errores 500 en NIM
                ))
            elif name.startswith("ollama/"):
                from src.core.config import settings
                real_name = name.replace("ollama/", "")
                models.append(ChatOllama(
                    model=real_name, 
                    base_url=settings.OLLAMA_BASE_URL,
                    temperature=kwargs.get("temperature", 0.0),
                    num_ctx=4096,
                    num_gpu=99
                ))
            else:
                import os
                from langchain_openai import ChatOpenAI
                
                clean_kwargs = kwargs.copy()
                clean_kwargs["default_headers"] = {
                    "HTTP-Referer": "http://localhost:8000",
                    "X-Title": "BMO Agent"
                }
                
                api_key = os.getenv("OPENROUTER_API_KEY")
                models.append(ChatOpenAI(
                    model=name, 
                    api_key=api_key, 
                    base_url="https://openrouter.ai/api/v1", 
                    **clean_kwargs
                ))
                
        return models

    @classmethod
    def _bind_and_fallback(cls, models, tools, response_format):
        """Aplica herramientas, formatos estructurados y políticas de fallback a la lista de modelos."""
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
        """Modelo principal de razonamiento pesado."""
        if tools is not None:
            # LISTA DE MODELOS A PRUEBA DE BALAS PARA TOOL CALLING
            tool_models = [
                "qwen/qwen3-coder-480b-a35b-instruct",
                "meta/llama-4-maverick-17b-128e-instruct",
                "bytedance/seed-oss-36b-instruct"
            ]
            models = cls._build_models_from_names(tool_models)
        else:
            models = cls._build_models_from_names(cls.HEAVY_MODEL_NAMES)
            
        return cls._bind_and_fallback(models, tools, response_format)

    @classmethod
    def create_lite(cls, tools = None, response_format: Optional[Type[BaseModel]] = None) -> BaseChatModel:
        """Modelo rápido para resumen, extracción y clasificación liviana."""
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
