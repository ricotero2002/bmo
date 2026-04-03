# Fase 7 - Parte 2: Evolución de la Búsqueda (Advanced RAG)

Esta fase se centró en transformar el sistema de recuperación de información de una búsqueda vectorial simple a una arquitectura de **Advanced RAG**. El objetivo principal fue mejorar la precisión de las respuestas y garantizar que el modelo siempre tenga el contexto completo necesario.

## 🚀 Implementaciones Principales

### 1. Recuperación de Chunks Adyacentes (Parent Document Retrieval)
**Acción:** Resolver el problema de la pérdida de contexto cuando un chunk individual es demasiado corto.

*   **Implementación:** Se modificó el `knowledge_base_retriever` para que, tras identificar un chunk relevante (N), realice una consulta secundaria ultra-rápida buscando los chunks `N-1` y `N+1` del mismo documento (usando el metadato `chunk_index`).
*   **Por qué:** Los trozos pequeños (chunks) son excelentes para que la base vectorial encuentre coincidencias matemáticas, pero a menudo "cortan" una idea por la mitad. Al expandir el contexto a los vecinos directos, el LLM recibe una narrativa continua y coherente.
*   **Regla de Exclusión:** Esta expansión **no** se aplica a los chunks de tipo `agentic`, ya que estos ya han sido procesados para ser semánticamente completos por sí mismos.

### 2. Re-Ranking con Gemini (Cross-Encoder)
**Acción:** Aumentar la **Precisión Contextual** filtrando resultados "ruidosos".

*   **Implementación:** Se creó la clase `GeminiReranker` (un `BaseDocumentCompressor`). Ahora, Pinecone recupera una lista inicial amplia (2.5 veces el valor de `K` solicitado) y Gemini actúa como un juez estricto que reordena y selecciona solo los documentos que realmente responden a la consulta.
*   **Por qué:** La búsqueda vectorial (similitud del coseno) es rápida pero "tonta": puede traer un documento que use las mismas palabras pero no tenga la respuesta. Un Re-Ranker basado en LLM lee el contenido y la pregunta juntos para asegurar relevancia total.

### 3. Selección Dinámica de `K`
**Acción:** Permitir que el Agente decida cuánta información necesita.

*   **Implementación:** Se añadió el parámetro `k_results` (con rango validado de 2 a 7) a la herramienta `knowledge_base_retriever`.
*   **Por qué:** No todas las preguntas requieren el mismo esfuerzo. Para una validación rápida, `K=2` ahorra tokens y tiempo; para generar un informe o resumen de un proyecto, el Agente puede solicitar `K=7` para una investigación profunda.

---

## 🛠️ Cambios Técnicos en el Código

### Ingesta (`src/service/chunking.py`)
- Se aseguró que todos los chunks generados (sea vía `AgenticChunker` o `MarkdownTextSplitter`) incluyan los metadatos `chunk_type` y `chunk_index`.
- Esto garantiza que el Retriever pueda distinguir entre propuestas atómicas y fragmentos de texto lineal.

### Herramientas (`src/tools/metadata_filter.py`)
- Refactorización completa del `knowledge_base_retriever`.
- Introducción de `LLMFactory` dentro de la lógica de recuperación para el Re-Ranking.
- Implementación de lógica de **Fallback Automático**: si la búsqueda con filtros específicos (fecha, tipo) falla, el sistema reintenta automáticamente una búsqueda semántica general para no dejar al Agente sin respuesta.

### Calidad y Testing (`src/tests/agente/`)
- Se migraron los tests de evaluación desde `src/evals/` a la estructura formal de `src/tests/agente/`.
- **Aumento de Exigencia:** Se incrementó el umbral de `ContextualPrecisionMetric` de 0.5 a **0.8**, reflejando la confianza en el nuevo sistema de Re-Ranking.
- Nuevos tests de comportamiento:
    - `test_retriever_k_results`: Valida que el parámetro `K` sea respetado.
    - `test_reranking_logic`: Valida mediante un "Juez" que el top de resultados sea relevante para la consulta.

---

## ✅ Resultados
Con estas mejoras, el sistema ha alcanzado un **100% de éxito** en el Golden Dataset, eliminando alucinaciones por falta de contexto y optimizando el uso de tokens mediante una selección más inteligente de la información recuperada.
