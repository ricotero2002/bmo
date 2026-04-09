# Optimizaciones a realizar

### Fase 1: Memoria Jerárquica y Metadatos (`agent.py`)

Actualmente, tu agente maneja el estado de los mensajes en el grafo, pero acumula todo el historial sin compresión. Vamos a implementar un patrón de **Memoria en Dos Niveles**.

**1. Modificación del Estado (`src/schemas/graph_state.py`):**

**2. Nodo de "Run Summarization" (Resumen de Turno):**
* **Lógica:** Al final de cada turno (justo antes de llegar a `END` en tu grafo de LangGraph), puede ser en cleanup o despues, se tomará el plan generado (`task_plan`), las llamadas a herramientas y el output final.
* **Acción:** El LLM generará un string: *"El usuario pidió X. Usé la herramienta Y porque Z. El resultado fue W (no w completo solo la idea)"*.
* **Metadato:** Este mensaje se guarda con `{"type": "summarize run"}`.

**3. Nodo de "Global Summarization":**
Quizas el sumarrize o otro
Si `len([m for m in messages if m.type == "human"]) > 4` (es decir, más de 12 mensajes en total contando inputs, outputs y resumenes).
* **Acción:** El LLM toma todos los `summarize run` viejos y los colapsa en un solo mensaje de sistema.
* **Metadato:** `{"type": "summarize global"}`.
* **Limpieza:** Se eliminan de la memoria corta todos los mensajes, conservando únicamente el `summarize global` y el último trío de mensajes recientes (ultimo input/output/summarize run).

---

### Fase 2: Golden Dataset V2 Expansivo (`golden_dataset_v2.py`)

El dataset actual tiene entradas de *brainstorming* y notas de reuniones. Vamos a escalar la complejidad simulando un entorno corporativo real.

**Nuevos Archivos a Ingestar (Ejemplos):**
1.  **Doc A:** Notas de 3 reuniones distintas con el equipo de DevOps sobre migraciones a Kubernetes.
2.  **Doc B:** Requisitos técnicos del framework LangGraph.
3.  **Doc C:** Historial de correos sobre problemas de facturación en AWS.
4.  **Doc D:** Documentación de una API interna.

**Estructura de las Nuevas Preguntas (Multi-hop):**
* **Nivel 1 (Semántico + Web):** *"En mis notas de la reunión de DevOps se mencionó un error con KEDA. Búscame en la web cuál es la última versión de KEDA y comparala con la que anoté."*
* **Nivel 2 (Multi-Semántico + Análisis):** *"Recuperame las notas de las reuniones (source doc 1) y (source doc 2). Hacé un análisis de qué tareas quedaron pendientes respecto al framework LangGraph."*
* **Nivel 3 (Semántico + Análisis + Planificación):** *"En base a las tareas que anoté que debo hacer con LangGraph esta semana, armame una planificación completa por fases."*

---

### Fase 3: Evaluación de Coherencia Conversacional (`test_rag_agentic.py`)

Actualmente, tus tests en `test_rag_agentic.py` utilizan DeepEval para probar consultas aisladas contra el dataset. Necesitamos probar que la memoria jerárquica de la Fase 1 funciona.

**Nueva Suite de Tests (`test_multiturn_rag`):**
* **Manejo de Hilo:** Debes usar un mismo `thread_id` a lo largo de un test para mantener el estado en la base de datos (PostgreSQL/Checkpointer).
* **Flujo de Prueba (Ejemplo de 4 pasos):**
    1.  *Input:* "Extrae mis notas sobre Kubernetes." (Verifica: Contextual Precision).
    2.  *Input:* "¿Qué versión anoté ahí?" (Verifica: Coreferencia, el agente debe saber que "ahí" es Kubernetes).
    3.  *Input:* "Busca en la web si esa versión está deprecada." (Verifica: Uso de tool basado en memoria).
    4.  *Input:* "Resume todo lo que hablamos hoy." (Verifica: `GlobalSummarizer` y coherencia).
* **Evaluación:** Al final del hilo, usas un `GEval` de DeepEval pasándole el historial completo para evaluar si el agente mantuvo la coherencia sin perder información clave.

---

### Fase 4: Stress Test Avanzado (`locustfile.py` y `endpoints.py`)

Vamos a subir el calor. Tu configuración actual permite 20 tareas concurrentes en FastAPI a través del `llm_semaphore` y prueba con 4 tipos de preguntas simples con Locust.

**1. Ajustes en la API (`endpoints.py`):**
* Aumenta `asyncio.Semaphore(20)` a `asyncio.Semaphore(26)`. Asegúrate de que el límite de memoria del Pod en Kubernetes (YAML) esté configurado para absorber este incremento (idealmente > 2Gi).

**2. Nuevo Script de Locust (`stress_test_v2.py`):**
* Aumentar la concurrencia objetivo a **50 usuarios**.
* **Sistema de Pesos:** Usar la funcionalidad de pesos en las tareas de Locust (`@task(weight)`) para simular tráfico realista. A mayor complejidad, menor probabilidad de ocurrencia para no reventar la base de datos vectorial de forma irreal.

**Esquema de Tareas Locust:**
* `@task(10)` **(Bajo Peso - Frecuente):** Solo búsqueda semántica en los Golden Datasets (Ej: *"¿De qué trata el Doc A?"*).
* `@task(5)` **(Peso Medio):** Búsqueda Web exclusiva (Ej: *"Busca el clima en Argentina"*).
* `@task(3)` **(Alto Peso - Complejo):** Combinado (Semántico + Web) (Ej: *"Busca en mis notas la versión de Python y luego busca en la web su fecha de fin de soporte"*).
* `@task(1)` **(Máximo Peso - Ultra Complejo):** Búsqueda + Análisis + Guardar (Ej: *"Analiza mis notas de la reunión, armá un resumen y usá la herramienta de guardado para crear una nota nueva en la base de datos"*).

### Datasets
Actualizar los documentos para que funcionen bien el tema de fachas y referencias a documentos, apararte hacerlos un poco mas grandes. Tambien hacer las notas mas desorganizadas y los documentos de api mas estructuradas:
¡Excelente paso! Expandir tus casos de prueba y crear una suite conversacional (multi-turno) es exactamente lo que consolida un sistema RAG en un producto *Enterprise*. Como el agente de BMO procesa el historial y resume, necesitamos datos que lo pongan a prueba.

Aquí tienes los *Golden Datasets* listos para ser integrados en tu código.

### 1. Actualización para `golden_dataset_v2.py` (Fase 2)

Agrega estos diccionarios a tu lista `GOLDEN_DATASET` en `golden_dataset_v2.py`. He redactado los textos simulando un entorno corporativo realista, con ruido semántico y referencias cruzadas para forzar los "multi-hops".

```python
# --- NUEVOS DATASETS CORPORATIVOS (FASE 2) ---

    {
        "name": "Doc A: Notas de Reuniones DevOps (K8s)",
        "category": "meeting_notes",
        "raw_text": (
            "Acta de reuniones equipo DevOps - Migración a Kubernetes.\n"
            "Reunión 1 (02/04/2026): Se debatió la arquitectura de despliegue. Decidimos usar Oracle OKE en lugar de AWS EKS para reducir costos.\n"
            "Reunión 2 (05/04/2026): Tuvimos un crasheo masivo en los workers de Celery durante la prueba de carga. El log mostraba un error crítico con KEDA al intentar leer el lag del broker de Kafka en Aiven. Estamos usando KEDA v2.12.0 y parece tener un bug específico con la autenticación SASL_SSL bajo alta concurrencia.\n"
            "Reunión 3 (07/04/2026): Definimos las tareas pendientes para la semana que viene: 1. Investigar si hay una versión más nueva de KEDA que solucione el bug. 2. Implementar el PostgreSQL checkpointer para la persistencia del estado de LangGraph. 3. Rotar los secretos en Infisical."
        ),
        "ideal_chunks": [
            "Acta de reuniones DevOps: En la Reunión 1 (02/04/2026) se decidió utilizar Oracle OKE en lugar de AWS EKS para la migración a Kubernetes con el fin de reducir costos.",
            "Reunión 2 (05/04/2026): Durante una prueba de carga, los workers de Celery crashearon debido a un error crítico de KEDA (versión v2.12.0) al leer el lag de Kafka en Aiven, aparentemente por un bug con autenticación SASL_SSL en alta concurrencia.",
            "Reunión 3 (07/04/2026): Las tareas pendientes son: 1) Investigar actualización de KEDA para solucionar el bug de SASL_SSL. 2) Implementar PostgreSQL checkpointer para LangGraph. 3) Rotar secretos en Infisical."
        ],
        "eval_query": "En mis notas de la reunión de DevOps se mencionó un error con KEDA. Búscame en la web cuál es la última versión de KEDA y comparala con la versión que anoté que usamos.",
        "expected_answer": "Anotaste que estás utilizando KEDA v2.12.0, el cual presentó un error con la autenticación SASL_SSL de Kafka. Según la búsqueda web, la última versión de KEDA es la [X.Y.Z]. Deberías actualizar desde la v2.12.0 a esta nueva versión para ver si el bug fue solucionado."
    },
    {
        "name": "Doc B: Requisitos Técnicos LangGraph",
        "category": "technical_doc",
        "raw_text": (
            "Documento de Arquitectura: Framework LangGraph para Agente BMO.\n"
            "El nuevo agente utilizará LangGraph para gestionar un flujo de trabajo multi-agente (Agentic Workflow). Necesitamos que el sistema sea capaz de recuperarse de errores de las herramientas (Tool Fallbacks).\n"
            "Tareas pendientes exclusivas del framework LangGraph:\n"
            "- Desarrollar el nodo 'Task Planner' para que el agente estructure sus pasos antes de ejecutar herramientas.\n"
            "- Integrar el sistema de 'Global Summarization' para inyectar contexto a los chunks huérfanos.\n"
            "- Solucionar el problema del límite de recursión (RecursionLimit) que ocurre cuando falla la búsqueda semántica repetidas veces."
        ),
        "ideal_chunks": [
            "El agente BMO utilizará LangGraph para flujos de trabajo multi-agente, requiriendo capacidad de recuperación de errores (Tool Fallbacks).",
            "Tareas pendientes para LangGraph: 1) Desarrollar el nodo 'Task Planner' para estructurar pasos. 2) Integrar 'Global Summarization' para inyectar contexto. 3) Solucionar el límite de recursión (RecursionLimit) ante fallos repetidos de búsqueda semántica."
        ],
        "eval_query": "Recuperame las notas de las reuniones de DevOps y los requisitos de LangGraph. Hacé un análisis cruzado de qué tareas quedaron pendientes respecto al framework LangGraph en ambos documentos.",
        "expected_answer": "Haciendo un análisis de ambos documentos, las tareas pendientes para el framework LangGraph son: 1) Implementar el PostgreSQL checkpointer para la persistencia del estado (mencionado en las notas de DevOps). 2) Desarrollar el nodo 'Task Planner'. 3) Integrar el 'Global Summarization'. 4) Solucionar el problema del límite de recursión (RecursionLimit)."
    },
    {
        "name": "Doc C & D: Ruido de Facturación y APIs",
        "category": "internal_wiki",
        "raw_text": (
            "Historial de AWS: La factura de marzo subió un 20% por transferencia de datos en el NAT Gateway, hay que revisar las VPCs.\n\n"
            "Documentación API: El endpoint /api/ask/stream requiere un token JWT en el header Authorization. Retorna un flujo Server-Sent Events (SSE) con los fragmentos de la respuesta del LLM."
        ),
        "ideal_chunks": [
            "La factura de AWS de marzo aumentó un 20% debido a la transferencia de datos en el NAT Gateway; se requiere revisión de las VPCs.",
            "El endpoint de la API interna /api/ask/stream exige un token JWT en el header Authorization y devuelve un flujo Server-Sent Events (SSE) con la respuesta del LLM."
        ],
        "eval_query": "En base a las tareas que anoté que debo hacer con LangGraph esta semana, armame una planificación completa por fases.",
        "expected_answer": "Planificación para LangGraph:\nFase 1 (Persistencia): Implementar el PostgreSQL checkpointer.\nFase 2 (Estructura central): Desarrollar el nodo 'Task Planner' para orquestar pasos.\nFase 3 (Contexto y Estabilidad): Integrar el sistema 'Global Summarization' y solucionar los errores de RecursionLimit en las búsquedas semánticas."
    }
```

---

### 2. Estructura para Pruebas Multi-Turno (Fase 3)

En `test_rag_agentic.py`, ahora necesitas una suite que ejecute un bucle sobre un historial de mensajes manteniendo el mismo `thread_id`. 

Aquí tienes la matriz de datos (`MULTI_TURN_DATASET`) y un esqueleto de cómo implementarlo con `DeepEval`.

```python
# --- NUEVA ESTRUCTURA PARA test_rag_agentic.py (FASE 3) ---

MULTI_TURN_DATASET = [
    {
        "test_name": "Coherencia Multi-Salto: Kubernetes, KEDA y Web",
        "turns": [
            {
                "input": "Extrae de mis notas un resumen de los problemas que tuvimos con KEDA en la migración a Kubernetes.",
                "expected_intent": "Recuperar información semántica del Doc A sobre el crasheo de los workers, el lag de Kafka y SASL_SSL.",
            },
            {
                "input": "¿Qué versión exacta de KEDA anoté ahí?",
                "expected_intent": "Evaluar la coreferencia. El agente debe saber que 'ahí' es el contexto recuperado en el turno anterior y responder 'v2.12.0'.",
            },
            {
                "input": "Busca en la web si esa versión tiene reportes conocidos de bugs con Kafka SASL.",
                "expected_intent": "El agente debe usar la herramienta de búsqueda web (DuckDuckGo) basándose en la versión 'v2.12.0' almacenada en la memoria a corto plazo.",
            },
            {
                "input": "Resume todo lo que hablamos hoy en una lista de tareas corta.",
                "expected_intent": "Evaluar el Global Summarizer y la memoria a largo plazo. Debe incluir la investigación de KEDA v2.12.0 y el resultado de la búsqueda web.",
            }
        ]
    }
]

# (Ejemplo de cómo adaptarlo en tu archivo de testing usando pytest)
# @pytest.mark.asyncio
# async def test_multiturn_coherence(rag_setup):
#     agent_service = rag_setup
#     thread_id = str(uuid.uuid4())
#     user_info = {"user_id": "evaluator_test"}
#     
#     chat_history_actual = []
#     
#     for turn in MULTI_TURN_DATASET[0]["turns"]:
#         # 1. Llamar al agente (usando astream_chat o ainvoke)
#         response = await agent_service.ainvoke(...)
#         chat_history_actual.append(f"User: {turn['input']}\nAI: {response}")
#     
#     # 2. Evaluación final de todo el hilo con DeepEval (GEval)
#     full_conversation = "\n".join(chat_history_actual)
#     
#     coherence_metric = GEval(
#         name="Conversational Memory & Multi-hop Coherence",
#         criteria="El agente debe mantener el contexto entre preguntas, resolver coreferencias (ej: 'esa versión') y usar la memoria para realizar búsquedas web.",
#         evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
#         model=GeminiJudge(...)
#     )
#     
#     test_case = LLMTestCase(
#         input=MULTI_TURN_DATASET[0]["turns"][-1]["input"], # Último input
#         actual_output=full_conversation # Se evalúa toda la charla
#     )
#     
#     assert_test(test_case, [coherence_metric])
```