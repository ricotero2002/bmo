# Documento de Arquitectura y Cambios: Proyecto BMO (Asistente Personal RAG)

## Fase 1: Cimientos de Contexto y Metadatos (Part 1)

Esta fase se centró en enriquecer semánticamente los datos antes de su inserción en la base de datos vectorial (Pinecone), asegurando que el LLM del agente reciba el mejor contexto posible durante la recuperación y optimizando los costos y el ruteo del Agentic Chunking.

---

### 1. Resumen Global Pre-Chunking (Contextual Retrieval)

Se implementó un analizador que procesa una muestra inicial de cada documento para extraer su "ADN" semántico antes de fragmentarlo.

**Cambios Implementados:**
* **Esquema Estricto de Extracción (`src/schemas/metadata.py`):** Se definió un contrato de datos usando Pydantic para estandarizar la clasificación.
    > [!IMPORTANT]
    > Se definieron tipos de documentos cerrados (`DocType`) como `meeting_notes`, `technical_doc`, etc., para garantizar que los filtros de metadatos en Pinecone funcionen con coincidencia exacta (exact match) sin alucinaciones de categorías.
* **`GlobalSummarizer` en `src/service/chunking.py`:** Un nuevo componente que analiza los primeros 5,000 caracteres (ajustable según tamaño) para determinar el tipo, resumen y fecha.
* **Inyección de Contexto Dinámica:** Cada fragmento (chunk) ahora se guarda con un prefijo: `[Contexto Global de {doc_type}: {global_summary}] \n\n {chunk_original}`.
    * **Por qué:** Resuelve el problema del "Chunk Huérfano" donde el LLM de recuperación no entiende de qué trata un párrafo porque perdió el título o el tema principal del documento original.

### 2. Ruteo Inteligente de Chunking (Efficiency & Cost Control)

Se delegó en el `GlobalSummarizer` la decisión técnica de qué estrategia de fragmentación utilizar, optimizando el balance entre costo y calidad.

**Cambios Implementados:**
* **`requires_agentic_chunking`:** Si el documento es detectado como "caótico" o "flujo de conciencia" (ej. notas rápidas, transcripciones desordenadas), se activa el `AgenticChunker`.
* **Fallback a Naive Chunking:** Para documentos estructurados (ej. manuales técnicos con markdown) o archivos extremadamente grandes (donde el costo de LLM sería prohibitivo), el sistema rutea automáticamente hacia el `MarkdownTextSplitter`.
    * **Por qué:** Reducir costos de API significativamente y evitar latencias innecesarias en documentos donde la estructura jerárquica ya es clara.
* **Limpieza de Metadatos Redundantes:** Al finalizar el chunking, se eliminan los campos `chunk_title` y `chunk_summary`.
    * **Por qué:** Con la inyección del Resumen Global en el texto, estos campos de metadatos se volvieron redundantes y consumían espacio/costo en los vectores de Pinecone sin aportar mejora en la búsqueda semántica.

### 3. Soporte para Fechas Históricas y Personalizadas

Se actualizó todo el pipeline de ingesta para que los documentos mantengan su valor temporal real, independientemente de cuándo fueron subidos al sistema.

**Cambios Implementados:**
* **Prioridad de Fecha:** El sistema ahora sigue este orden de precedencia: 
    1. `custom_date` (provisto manualmente por el usuario vía API).
    2. `document_date` (extraído automáticamente por el LLM del contenido del archivo).
    3. `ingest_date` (fecha actual del sistema como fallback final).
* **Integración en `knowledge_base_retriever`:** Se habilitó el filtro `$gte` (mayor o igual) en Pinecone para que el Agente pueda procesar comandos como "Busca notas de marzo de 2024 en adelante".
    * **Por qué:** Un asistente personal es inútil si no puede distinguir entre una nota de ayer y un plan de proyecto de hace dos años.

### 4. Robustez del Agente y "Auto-Fallback" (`metadata_filter.py`)

Se implementó una red de seguridad (safety net) para manejar los errores de razonamiento del LLM durante la búsqueda.

**Cambios Implementados:**
* **Retriever con Auto-Fallback:** Si el Agente aplica filtros muy agresivos (ej. buscar solo en `meeting_notes`) y Pinecone devuelve 0 resultados, la herramienta automáticamente **ignora los filtros** y realiza una segunda búsqueda puramente semántica.
    * **Por qué:** Evita la "Pereza del LLM" y errores por mala clasificación inicial. Si el dato existe pero el filtro lo bloqueaba, el Agente ahora lo encuentra igual y recibe un aviso: `[AVISO SISTEMA]: Se realizó fallback...`.
* **Corrección de Bucle Infinito (Infinite Loop Fix):** Se eliminaron las inyecciones de `AIMessage` con pensamientos internos que causaban que Gemini 2.5 Flash entrara en bucles de 65,000 tokens al intentar "terminar" oraciones que el sistema le había metido en la boca.
* **Secuencia de Mensajes Limpia:** Se adoptó el uso de prefijos `[SISTEMA]` en `HumanMessage` para dar feedback al agente tras un error de tool.
    * **Por qué:** Garantiza cumplimiento con la política estricta de Gemini de `User -> Model -> Tool -> Model`, evitando el error `400 INVALID_ARGUMENT`.

### 5. Suite de Evaluación con DeepEval (`eval_utils.py`)

Se refinó la forma en que medimos el éxito del sistema para que los resultados sean representativos de la experiencia real del usuario.

**Cambios Implementados:**
* **Acumulación de Contexto en `ask_my_rag`:** La función recolecta **todos** los documentos de **todas** las llamadas a herramientas hechas en un solo turno.
    * **Por qué:** Antes, si el Agente hacía dos búsquedas y la última fallaba, DeepEval recibía contexto vacío. Ahora recibe la suma de todo lo que el Agente leyó.
* **`GeminiJudge` Robusto:** Se agregó un limpiador de JSON para que el evaluador no falle si el LLM devuelve markdown (````json ... ````).
* **Ajuste de Umbrales (Thresholds):**
    * **Contextual Precision (0.5):** Se reconoció que al no usar un Re-Ranker, es aceptable que la respuesta esté entre los primeros resultados aunque no sea el #1 absoluto.
    * **Agentic Chunking (0.7):** Se relajó el criterio de coherencia dado que el procesamiento semántico tiende a refrasear el contenido original.

---
> [!TIP]
> Estos cambios transformaron un RAG básico en un sistema **Context-Aware** capaz de recuperarse de errores de búsqueda y mantener el hilo conductor del documento en cada pequeño fragmento de información.


feat(rag): implementar auto-fallback, resumen global y estabilización de evaluación

- Nueva lógica de Auto-Fallback en el retriever para búsquedas sin filtros si falla el primer intento.
- Implementación de GlobalSummarizer para inyectar contexto contextual en cada chunk.
- Eliminación de bucles infinitos en Gemini corrigiendo el orden de mensajes (HumanMessage [SISTEMA]).
- Refinamiento de la suite DeepEval para acumular contexto multi-turno en las métricas.
- Documentación técnica consolidada en docs/fase7.
