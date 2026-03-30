# Fase 7: Testing, Optimización y Análisis

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
