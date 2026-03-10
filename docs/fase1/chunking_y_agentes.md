# Core de Agentes y Chunking Adaptativo

Este documento detalla la arquitectura implementada en la fase 1.2 del proyecto, cuyo objetivo es dotar a la ingesta de documentos de una estrategia de división (chunking) inteligente impulsada por Modelos de Lenguaje Grandes (LLMs).

---

## 1. Módulo Core (`src/core`)

El módulo core abstrae la lógica de inicialización e interacción con los LLMs, utilizando el framework **LangGraph** y sus utilidades para agentes.

### 1.1 `AgentFactory` (`src/core/agent.py`)
En lugar de instanciar cadenas o modelos dispersos por la aplicación, centralizamos la creación de agentes a través de `AgentFactory.create()`. 

**Características de Resiliencia:**
1. **Reintentos Nativos (`.with_retry`)**: Utiliza variables estándar de LangChain para manejar fallas temporales (ej. límites de tasa o caídas de red) con un *backoff* exponencial (`wait_exponential_jitter=True`) limitando los intentos (`stop_after_attempt=3`).
2. **Sistema de Fallback (`ModelFallbackMiddleware`)**: Si el modelo primario falla permanentemente (ej. saldo agotado o caído temporalmente), el middleware captura el error y recurre automáticamente a un modelo de respaldo con menores capacidades pero estable.
   - *Primario:* `gemini-1.5-pro` (vía Google Generative AI).
   - *Fallback:* `gpt-4o-mini` (vía OpenAI).
3. **Salida Estructurada (`ProviderStrategy`)**: Soporta envolturas nativas (vía Pydantic) garantizando que el LLM del agente siempre devuelva un esquema JSON validado o un diccionario exacto.

**Integración en FastAPI:**
La fábrica `AgentFactory` no se instancia por petición. Se inyecta la *referencia* a la clase en `app.state.agent_factory` durante el ciclo de vida de arranque (`main.py`), permitiendo a las dependencias inyectar la fábrica en el Endpoint y de allí al Servicio sin acoplar lógicas de infraestructura.

### 1.2 Registro de Prompts (`src/core/prompts/`)
Los system prompts (directrices del LLM) se han desacoplado de la lógica de programación y radican en archivos individuales expuestos hacia una interfaz común (`__init__.py`). Esto facilita el control de versiones y afinar el desempeño:
- `propositions.py`: Cómo extraer conclusiones atómicas de un texto.
- `router.py`: Cómo vincular lógicamente si una nueva frase pertenece a un contexto establecido, o si necesita un chunk nuevo.
- `summaries.py` y `titles.py`: Prompts complementarios para mantener vivas y resumidas las abstracciones de los chunks en curso.

---

## 2. Dominio de Chunking (`src/service/chunking.py`)

No todos los documentos deben ser tratados con inteligencia artificial para ser fragmentados. Un libro gigante estructurado de 500 páginas arruinaría tu presupuesto (costos del proveedor LLM) si analizaras párrafo por párrafo.

Para resolverlo, hemos abstraído un **Router** en `ChunkingService.process()`.

### 2.1 Módulo `ChunkingRouter`
Utiliza una validación heurística. Si un documento entrante:
- Supera los 3.000 caracteres, **O**
- Es un formato estructurado pesado (`.pdf`, `.docx`), **O**
- Contiene indicios de esquemas Markdown (`# `, `## `)...

El enrutador decidirá que es un documento **Extenso/Estructurado**. En este caso, utiliza el divisor crudo y económico: `MarkdownTextSplitter` (divide contando caracteres asegurando solapamiento jerárquico).

En cualquier otro caso (Un post, una nota diaria, o texto de formato libre), activará y derivará el texto al **Agentic Chunker**.

### 2.2 `AgenticChunker` (Chunking Proposicional Inteligente)
Es el "cerebro" semántico de nuestra base de conocimiento. Funciona creando instantáneas dinámicas (`AgentFactory.create()`) adaptadas a esquemas de salida:
- Un agente "Limbo" responde texto simple.
- Un agente "Estructurador" está forzado a devolver un esquema de Lista (`Sentences`).
- Un agente "Enrutador" está forzado a devolver IDs (`ChunkID`).

**Ciclo de vida del Chunking Agéntico:**
1. **Descomposición:** Lee un párrafo y le pide al Agente que extraiga todas las afirmaciones atómicas (*propositions*) de variables complejas. Extrae nombres propios explícitos, quita pronombres e independiza hechos.
2. **Evaluación de Relevancia:** Por cada proposición atómica extraída, elabora un "Resumen de Todos los Chunks Existentes" (Outline) y le pide al Agente Enrutador que evalúe si la nueva afirmación pertenece semántica y lógicamente a uno de los contextos conocidos.
3. **Agrupación / Mutación:**
   - Si no pertenece, el agente elabora un **Resumen Nuevo** (1 línea) y un **Título Breve**, originando un nuevo *Chunk ID*.
   - Si pertenece a un chunk dado, se apila la oración atómica y el contexto sufre una mutación, forzando a re-crear un Resumen y un Título generalizado abarcando la nueva información en la bolsa.
4. **Almacenamiento:** Finalmente transfiere cada "concepto base" aglomerado a Objetos `Document` listos para los Embeddings vectoriales de ChromaDB.
