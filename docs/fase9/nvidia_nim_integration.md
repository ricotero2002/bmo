# Integración de NVIDIA NIM (Fase 9)

En esta fase se ha migrado la infraestructura de IA de BMO para utilizar los endpoints gratuitos de **NVIDIA NIM**, optimizando la precisión, latencia y costos del agente.

## 🚀 Cambios Principales

### 1. Modelos de Lenguaje (LLM)
Se ha actualizado `src/core/llm.py` para priorizar los modelos más potentes de NVIDIA:

*   **Heavy Agentic**: `meta/llama-3.1-405b-instruct` y `mistralai/mistral-large-2-instruct`.
*   **Reasoning**: **DeepSeek-R1** se ha configurado como el planificador primario por su capacidad superior de "cadena de pensamiento" (CoT).
*   **Lite / Routing**: `meta/llama-3.2-3b-instruct` y `google/gemma-2-9b-it` para tareas rápidas.
*   **Coding**: `mistralai/codestral-22b-instruct-v0.1`.

> [!NOTE]
> El código original de OpenRouter y Ollama se ha mantenido comentado para permitir un rollback rápido si fuera necesario.

### 2. Embeddings (RAG)
En `src/providers/vector_store/factory.py`, se reemplazaron los embeddings de Google por los de NVIDIA:
*   **Modelo**: `nvidia/nv-embedqa-e5-v5`.
*   Este modelo está optimizado para tareas de QA y búsqueda semántica en sistemas RAG.

### 3. Re-Ranking Abstracto
Se refactorizó `src/tools/metadata_filter.py` para introducir una `RerankerFactory`:
*   **NVIDIA Reranker**: Ahora es el motor predeterminado usando `nvidia/nv-rerankqa-mistral-4b-v3`.
*   **Gemini Reranker**: El motor "agentic" original basado en LLM sigue disponible como opción.
*   **Configuración**: Se puede alternar entre motores usando la variable de entorno `RERANKER_TYPE` (`nvidia` o `gemini`).

## 🛠️ Configuración Requerida

Para que el sistema funcione, es necesario añadir la siguiente variable de entorno al archivo `.env` o al entorno de ejecución:

```bash
NVIDIA_API_KEY=tu_api_key_aqui
```

## 📦 Dependencias
Se añadió el paquete oficial de integración al proyecto:
```bash
pip install -U langchain-nvidia-ai-endpoints
```
(Agregado automáticamente a `requirements/base.txt`).

---
*Documentación generada para la Fase 9 del proyecto BMO.*
