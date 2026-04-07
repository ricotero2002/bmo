Fase 1: Cimientos de Contexto y Metadatos (Victorias Rápidas)
Esta fase se centra en enriquecer los datos antes de que lleguen a la base vectorial, asegurando que el LLM tenga el mejor contexto posible.

Paso 1.1: Implementar Resumen Global Pre-Chunking (Opción A)

Acción: Crear un nodo o función justo antes de llamar a tu ChunkingRouter.

Implementación: Usar un modelo rápido y económico para analizar los primeros kilobytes del texto extraído. Pedirle que devuelva un JSON con doc_type y global_summary.

Integración: Inyectar el doc_type en la metadata del Document de LangChain. Modificar el page_content de cada chunk resultante para que empiece con algo como: [Contexto Global: {global_summary}] \n\n {chunk_original}.

el tittle y summary de cada chunk:
                "chunk_title": chunk_data['title'],
                "chunk_summary": chunk_data['summary'],
realmente nunca lo uso y no lo veo tan necesario como metadata, al terminar el chunking deberia eliminarse a mi parecer.

Tendria que considerar bien el largo del texto, porque capas 3000 es muy poco para una nota medianamente grande. Capas a la ves el llm que se encarga de anlizar el texto puede ver si el mismo es una nota desorganizada y necesita hacer el chunking agentic o no. Teniendo tambien en cuenta el largo y posibles costos.

Paso 1.2: Soporte para Fechas Personalizadas

Acción: Permitir que los documentos históricos mantengan su fecha real en lugar de la fecha de ingesta.

Implementación: Actualizar los endpoints de tu API para aceptar un campo document_date. Pasar este valor a través de los metadatos en orchestrator.py directo hacia la tarea de Celery, y finalmente usarlo en la función create_document de ingestion.py.

Paso 1.3: Redefinir la "Opción B" (Intención de Chunks) (Para luego)

Acción: En lugar de forzar a que cada chunk tenga una etiqueta estricta (que a veces es ambiguo), añadir un metadato más flexible durante el AgenticChunker.

Implementación: Pedirle al LLM que genera el título y resumen del chunk que agregue un arreglo de tags o palabras clave específicas de ese fragmento (ej. ["java", "spring boot", "comparativa"]). Esto es más útil para búsquedas por filtros exactos que intentar adivinar si es un "action_item".




Fase 2: Evolución de la Búsqueda (Retriever)
Una vez que los datos están bien guardados, hay que mejorar cómo los recuperamos, especialmente para documentos largos o consultas complejas.

Paso 2.1: Recuperación de Chunks Adyacentes (Parent Document Retrieval)

Acción: Resolver el problema de buscar en un libro o documento largo donde un chunk se queda corto de contexto.

Implementación: En lugar de devolver solo el chunk que hizo "match" vectorial, utiliza la metadata chunk_index que ya generas. Si el vector recupera el chunk 5, puedes hacer una consulta secundaria rápida para traer los chunks 4 y 6, concatenarlos, y darle al agente un contexto continuo más amplio.

Paso 2.2: Re-Ranking del Contexto

Acción: Mejorar la precisión (Contextual Precision) de los resultados devueltos por la base vectorial.

Implementación: Añadir un modelo de cross-encoder (como Cohere Rerank). La base vectorial devuelve los top 20 resultados, y el Re-Ranker los reordena quedándose con los top 5 más relevantes para la pregunta exacta del usuario antes de pasarlos a LangGraph.

Capas permitir que elija el k del retriver (con un min y max)



Fase 3: Expansión de Herramientas (Agentic Capabilities)
Aquí es donde el asistente pasa de ser un simple buscador a un agente proactivo.

Paso 3.1: Integración de Búsqueda Web (Fallback)

Acción: Permitir que el agente busque en internet si tus notas no tienen la respuesta.

Implementación: Crear una nueva herramienta (ToolNode en LangGraph) usando la API de Tavily o DuckDuckGo. Modificar tu _grade_documents o la lógica del agente para que, si el knowledge_base_retriever falla repetidamente, decida usar la herramienta de búsqueda web.

Paso 3.2: Herramienta de Escritura y Persistencia

Acción: Permitir que el agente guarde nuevas ideas, resúmenes o planificaciones que genere durante la charla.

Implementación: Crear una herramienta llamada save_note_to_knowledge_base. Cuando el agente la llame, ejecutará la misma lógica que tu orchestrator.py (crear un archivo en storage, encolar en Celery y vectorizar). Así, el asistente "aprende" de las conversaciones.

Paso 3.3: Soporte para Consultas Complejas (Planificación)

Acción: Orquestar preguntas multi-salto (ej. buscar notas, buscar en web, crear plan).

Implementación: Con las herramientas de RAG y Web ya funcionales, el LLM subyacente (si es suficientemente potente) podrá descomponer la tarea por sí solo. La clave aquí es ajustar tu System Prompt para indicarle explícitamente que está autorizado a usar múltiples herramientas secuencialmente para armar planes complejos.


Agregar que siempre se pongan todas las sources en los resultados (base de conocimientos o link) y que se puedan acceder tipo link y puedas ver el archivo (te lo traes del storage) o te redirigis al link. Esta segunda parte seria del frontend pero hay que hacer las modificacion en el bakcend para obtener el link presigned (el temporal) y la forma del source.



Fase 4: Evaluación Continua y Automatización
Para asegurar que todo lo anterior no rompa nada y sea escalable.

Paso 4.1: Pipeline de Sincronización Automática (Drive/Carpetas)

Acción: Dejar de subir archivos a mano.

Implementación: Crear un cronjob en Kubernetes o una tarea periódica en Celery (Celery Beat) que escanee una carpeta local o una conexión a Google Drive. Si detecta archivos nuevos o modificados, dispara la ingesta automáticamente hacia Kafka/Celery.

Paso 4.2: Interfaz de "Human in the Loop"

Acción: Recolectar feedback directo del usuario sobre las respuestas.

Implementación: En la interfaz de chat, añadir botones de 👍/👎. Si el usuario marca algo como incorrecto y provee la corrección, guardar ese par (Pregunta, Respuesta Ideal) en una base de datos relacional (PostgreSQL).

Paso 4.3: Testing Automatizado con Golden Datasets

Acción: Probar el sistema de forma masiva contra regresiones.

Implementación: Usar los pares guardados en el paso anterior (y generados sintéticamente como el ejemplo que te di antes) para crear un suite de pytest. Puedes usar otro LLM para que actúe como "Juez" y evalúe si la respuesta que está devolviendo tu API actual coincide semánticamente con la respuesta esperada del Golden Dataset.




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


python -m pytest src/evals/test_rag_agentic.py::test_rag_performance -k goldcase1 -v -s