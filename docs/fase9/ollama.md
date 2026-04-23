1. Actualización de tu llm.py (La Red de Seguridad Híbrida)
Vamos a configurar LangChain para que use estos modelos optimizados.
Python
from typing import Optional, Type
from pydantic import BaseModel
from langchain_openrouter import ChatOpenRouter
from langchain_ollama import ChatOllama
from langchain_core.language_models.chat_models import BaseChatModel

class LLMFactory:
    """Fábrica de modelos nativa usando OpenRouter y fallbacks locales optimizados."""

    # 1. El Planner y Judge (Tareas complejas) usarán Llama 3.2 1B si falla la nube
    HEAVY_MODEL_NAMES = [
        "nousresearch/hermes-3-llama-3.1-405b:free",
        "meta-llama/llama-3.3-70b-instruct:free",
        "qwen/qwen3-next-80b-a3b-instruct:free",
        "ollama/llama_1b_gpu"  # <-- Tu modelo de 1.2GB optimizado (Llama 3.2 1B)
    ]

    # 2. El Router o extractor (Tareas básicas) usará Qwen 0.5B para ser rapidísimo
    LITE_MODEL_NAMES = [
        "google/gemini-2.0-flash-lite-preview-02-05:free",
        "google/gemini-2.0-pro-exp-02-05:free",
        "ollama/qwen_force_gpu"  # <-- Tu modelo de 400MB optimizado (Qwen 0.5B)
    ]
    
    # ... (PLANNER_PRIMARY, JUDGE_PRIMARY, etc. quedan igual) ...

    @classmethod
    def _build_models_from_names(cls, model_names: list[str], **kwargs) -> list[BaseChatModel]:
        """Construye las instancias dinámicamente inyectando parámetros de hardware local."""
        models = []
        for name in model_names:
            if name.startswith("ollama/"):
                real_name = name.replace("ollama/", "")
                
                # INYECCIÓN DE HARDWARE: LangChain enviará estos parámetros a la API de Ollama
                models.append(ChatOllama(
                    model=real_name, 
                    temperature=kwargs.get("temperature", 0.0),
                    num_ctx=1024,  # <-- Límite VITAL para tu GTX 950
                    num_gpu=99     # <-- Fuerza el uso del 100% de la GPU
                ))
            else:
                # Lógica para OpenRouter (sin x_title para evitar errores)
                clean_kwargs = kwargs.copy()
                if "x_title" in clean_kwargs:
                    del clean_kwargs["x_title"]
                clean_kwargs["default_headers"] = {
                    "HTTP-Referer": "http://localhost:8000",
                    "X-Title": "BMO Agent"
                }
                models.append(ChatOpenRouter(model=name, **clean_kwargs))
                
        return models

    # ... (El resto del archivo queda igual) ...


2. ¿Cómo interactúa FastAPI (Docker) con Ollama (Windows)?
Tienes FastAPI corriendo dentro de un contenedor Docker en k3d, y Ollama corriendo directamente en tu Windows. Por defecto, un contenedor no sabe cómo hablarle al sistema anfitrión.
Para que tu contenedor alcance el puerto 11434 de Ollama en tu Windows:
Abre tu archivo main.py.
Busca si en alguna parte estás configurando la variable de entorno OLLAMA_HOST o si LangChain lo está infiriendo automáticamente.
LangChain por defecto busca Ollama en localhost:11434. ¡Pero "localhost" dentro de Docker es el propio contenedor!
Debes asegurarte de que tu código Python o tus variables de Kubernetes apunten a http://host.k3d.internal:11434 (o host.docker.internal).
Si no quieres tocar Kubernetes, puedes forzarlo en código al inicio de main.py:
Python
import os
# Redirige todo el tráfico local de Ollama hacia el anfitrión Windows
os.environ["OLLAMA_HOST"] = "http://host.k3d.internal:11434"


75: 3. Rutina de Arranque de Servidor (Tu nuevo hábito diario)
76: Como usamos la magia de Vulkan para bypasear la antigua arquitectura de tu GPU, este será el ritual que debes seguir siempre antes de ponerte a programar tu agente:
77: Abre un PowerShell normal de Windows.
78: Escribe `$env:OLLAMA_VULKAN="1"` y dale Enter.
79: Escribe `$env:OLLAMA_HOST="0.0.0.0"` y dale Enter (OBLIGATORIO para que Docker lo vea).
80: En esa misma consola, escribe `ollama serve` y dale Enter.
81: (Opcional: Minimiza esa ventana para que no te estorbe).
Ahora sí, levanta tu clúster de K3d, tu Docker Compose, o tu Airflow.
Si omites el paso 2, Ollama intentará usar CUDA nativo y te dará el error 0xc0000005 (el pantallazo azul de la IA) apenas FastAPI le envíe el primer prompt de fallback.
