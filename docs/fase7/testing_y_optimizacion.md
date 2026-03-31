# Fase 7: Testing, Optimización y Análisis
Tengo que probar si funciona bien el resumen ahora.


Esta fase está dedicada a asegurar que el asistente y su integración con Kubernetes sean rápidos, económicos, certeros y escalables antes de dar por finalizado el núcleo del proyecto. 

A continuación se detalla todo el espectro de pruebas, mediciones y optimizaciones a realizar:

## 1. Pruebas de Calidad de Ingesta y Recuperación (RAG)
* **Tests de Ingesta Masiva:** Crear y cargar decenas o cientos de notas/documentos PDF de forma simultánea. Observar cómo se comportan los workers y Kafka ante esta carga en ráfagas.
* **Calidad de Embeddings:** Verificar que los chunks extraídos y generados tengan un sentido semántico fuerte y no se corten conceptos a la mitad.
* **Métricas de Recuperación:** Medir el *Contextual Precision* y *Contextual Recall* en los documentos devueltos.
* **Filtros por Metadatos:** Comprobar que la búsqueda restringida (ej. búsqueda sólo en documentos recientes o de cierta categoría) funcione perfectamente en la BD Vectorial.

## 2. Pruebas de Calidad del Agente (LLM)
* **Prevención de Alucinaciones:** Realizar preguntas engañosas o sobre temas totalmente inexistentes en los documentos para asegurar que el agente reconozca que no sabe la respuesta, en lugar de inventarla.
* **Preguntas Complejas/Multi-salto:** Hacer preguntas que requieran relacionar y sintetizar información distribuida en dos o más documentos distintos (Reasoning).
* **Coherencia del Historial:** Verificar que el LLM recuerda el contexto de la conversación (memoria de LangGraph) sin mezclar datos de chats anteriores.

## 3. Análisis de Latencias y Tiempos de Respuesta
* **Latencia de Ingesta:** El tiempo transcurrido desde que se sube un documento hasta que sus vectores están disponibles y listos para consultar.
* **Time-to-First-Token (TTFT):** Medir de forma estricta cuánto tarda el LLM en empezar a emitir la primera palabra en la interfaz usando Streaming (SSE).
* **Latencia de Búsqueda Vectorial:** El tiempo que demora la consulta de similitud antes de que el texto pase al LLM.

## 4. Análisis de Costos y Consumo de Recursos
* **Eficiencia de Costos de LLMs:** Monitorear el consumo de tokens (Prompt tokens vs Completion tokens) en cada interacción usando los distintos modelos configurados. Proyectar un costo mensual estimado en USD para uso intensivo y uso casual.
* **Recursos en Kubernetes Local (K3d):** Monitorear y registrar la RAM y CPU consumidas por todo el stack local (API, Celery Workers, Kafka, PostgreSQL, OpenTelemetry, etc.) en reposo vs carga.
* **Comparativas Cloud:** Estimar los costos reales operativos simulando un entorno AWS (EKS y base de datos gestionada) frente a los nodos Oracle Cloud "Always Free" Ampere A1.

## 5. Pruebas de Estrés y Escalabilidad (Stress Testing)
* **Simulación de Tráfico:** Utilizar herramientas simples para simular 10, 50 o 100 consultas simultáneas al agente.
* **Comportamiento del Autoescalado (KEDA + HPA):** Validar observando OpenTelemetry/Grafana si los pods de la API y los workers se replican correctamente en cuanto la CPU promedio supera el 70% o la pila de Kafka/Celery acumula retraso (Lag).

## 6. Mejoras Futuras y Ajuste Fino
* **Búsqueda en Internet (Web Search):** Evaluar darle al agente una herramienta extra (Tavily/DuckDuckGo) para que busque en la web abierta cuando no encuentre respuestas en tus notas locales.
* **Optimización de Prompts:** Reducir la longitud del *System Prompt* base sin perder la caracterización del asistente, ahorrando así tokens en el historial.
* **Re-Ranking de Contexto:** Explorar modelos de reranking (como Cohere) para perfilar aún más los chunks que recibe el LLM luego de la búsqueda vectorial.



Algunas cosas a mejorar pueden ser el tema de:
Hacer que si tiene que buscar entre muchos chunks (ponele un libro) pueda pedir mas chunks o chunks adyacentes.

muchas pruebas, pedirle muchos documentos a gemini (con diferetnes fechas despues ver como hacer esto) subirlos y hacer pytest haciendo que busque lo mas importante.

Poder incluir en tipo los Golden data sets, que el usuario puede indicar che esto está mal así después se analiza y añade corregido, y human in the loop

En el chunking aprovechando que hago chunking agentic que lo que resume de cada parrafo lo ponga en los chunking junto al  contexto, asi por ejemplo (y tabmbien viendo el titulo), asi si por ejemplo es una reunion anota de reunion tanto asi al hacer busqueadas puede encontrarlo o un metadato con contexto sobre que trata, el tema que tengo que ver con documentos ocmpletos, capas usando los primeros chunks como contexto.

Permitir preguntas complejas como busca estas notas, despues segun los freworks o cosas que tengo que hacer (como un proyecto de x) busca en internet sobre esos y haceme una planificacion mediana de que hacer con todo eso.

Permitir que el agente luego escriba o guarde documentos sobre cosas hablandas para poder recuperarlas luego.

Hacer si o si el pipeline de obtener documentos de una carpeta o de un drive.

Aquí te dejo opciones viables y estructuradas para implementar esto en tu código, junto con los datos de prueba que pediste.

1. Estrategias para Mejorar el Chunking y el Contexto
Dado que ya tienes un enrutador (ChunkingRouter) y un AgenticChunker, podemos atacar el problema en dos frentes: Metadatos Duros (para filtros exactos) y Enriquecimiento Semántico (para mejor similitud vectorial).

Opción A: Resumen Global Pre-Chunking (Recomendado)
Antes de pasar el texto por el MarkdownTextSplitter o el AgenticChunker, toma los primeros N caracteres del documento (o el documento entero si es corto) y pásalos por un LLM muy rápido (como un modelo Flash o Haiku) con un prompt sencillo:

Objetivo: Extraer el tema general y el tipo de documento.

Output esperado (JSON): {"doc_type": "meeting_notes" | "class_notes" | "todo_list" | "general", "global_summary": "Breve resumen de 2 líneas"}.

Implementación: Inyectas este doc_type como metadato duro en Pinecone (ideal para cuando el agente decide usar el filtro source_filter). Además, pre-pendes el global_summary al page_content de cada chunk. Así, un chunk que solo dice "Revisar el bug de login" se convierte vectorialmente en: Contexto: Notas de reunión de sincronización de equipo. Texto: Revisar el bug de login.

Opción B: Evolucionar el AgenticChunker
Aprovechando que tu AgenticChunker ya usa un LLM para generar un title y un summary de cada proposición agrupada, puedes agregar un campo al esquema Pydantic para que clasifique la intención de ese chunk específico:

chunk_intent: "action_item", "concept_explanation", "reference_data".

Esto es útil porque una nota de clase puede contener tanto explicaciones (conceptos) como tareas ("leer capítulo 4").

2. ¿Cómo manejar fechas históricas/personalizadas?
Actualmente, tu sistema pisa cualquier fecha con el momento exacto de la subida.
En ingestion.py, tienes esto:
"created_at": datetime.now(timezone.utc).timestamp()

Y en orchestrator.py:
"uploaded_at": datetime.now(timezone.utc).isoformat()

La solución:

Modificar la API/Frontend: Permite que al subir el archivo se envíe un campo opcional document_date o reference_date.

En el Orchestrator: Recibe ese dato en el diccionario metadata. Tu código actual ya hace job_metadata.update(metadata), lo cual está perfecto. Solo asegúrate de pasar ese metadata (o específicamente la fecha) como argumento extra (kwargs) a la tarea de Celery (process_document_task.apply_async).

En Ingestion: Modifica create_document para que acepte un parámetro custom_date.

Python
def create_document(self, text: str, filename: str, custom_date: float = None, ...):
    timestamp = custom_date if custom_date else datetime.now(timezone.utc).timestamp()
    metadata = {"source": filename, "created_at": timestamp}
De esta forma, si subes notas del año pasado, el retriever podrá usar el filtro date_from correctamente.