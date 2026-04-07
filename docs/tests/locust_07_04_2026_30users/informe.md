1. ¿Fue exitoso el test? (El Veredicto)
Absolutamente SÍ.
Es un éxito rotundo a nivel de infraestructura. En el archivo de Locust vemos 136 chats y 16 ingestas masivas con 0 fallos reales en la lógica. El sistema no se cayó, la base de datos no se bloqueó y los workers procesaron los documentos.

Los logs de la terminal donde ves los 503 Service Unavailable y WARNING: Exceeded concurrency limit no son errores, son el escudo de tu sistema. Al usar el límite de Uvicorn o el Semáforo, el servidor hizo "Load Shedding" (rechazó carga extra elegantemente) en lugar de intentar procesarlo todo y morir por falta de memoria. Esto es exactamente lo que hace Netflix o Amazon en Black Friday.

2. Análisis de las Métricas Clave
Extraje los datos exactos de tus CSV de Locust y LangSmith:

TTFT (Time To First Token):

Mediana: 4.6 segundos | Máximo: 14.9 segundos.

Análisis: Excelente. Considerando que el agente primero tiene que pensar (Task Planner), vectorizar la pregunta, ir a la base de datos (Pinecone), recuperar chunks, evaluar si sirven y recién ahí empezar a generar, 4.6 segundos bajo estrés masivo es una latencia tremenda.

Tiempo Total de Chat:

Mediana: 48 segundos | Promedio: 53.7 segundos | Máximo: 100 segundos.

Análisis: Es alto, pero normal en flujos asíncronos complejos (RAG). El cliente de Locust esperó hasta 1.5 minutos por las respuestas más largas, y la conexión HTTP se mantuvo estable (gracias al timeout que configuramos).

Ingesta de Documentos (Archivos Pesados):

Mediana: 3.6 segundos | Máximo: 7.4 segundos.

Análisis: Impecable. Tu endpoint de FastAPI solo recibe, guarda en OCI y manda a Kafka súper rápido. El worker hace el trabajo pesado en el fondo sin bloquear al usuario.

Costos y Tokens (LangSmith):

Total de Runs: 177 interacciones.

Tokens Procesados: ~2.33 Millones de tokens.

Costo Total: $0.247 USD (Menos de 25 centavos de dólar).

Análisis: Tu arquitectura es increíblemente barata. Estás en un promedio de $0.0014 por respuesta con RAG incluido.

3. ¿El cuello de botella es la lógica o los recursos?
Son 100% los recursos físicos y la red externa.
Tu lógica (FastAPI asíncrono + Celery + LangGraph) escala perfectamente. El problema es que cada hilo activo de LangGraph clona cadenas pesadas en la RAM. Además, tu CPU pasa la mayor parte del tiempo "durmiendo" (I/O Bound) mientras espera que la API de Gemini/OpenAI o la base vectorial respondan.

4. Sobre la Concurrencia: ¿Podemos aumentar a más de 20 tareas por Pod?
Sí, matemáticamente se puede, pero requiere hardware.
Actualmente, cada petición viva consume unos 40 MB a 50 MB de RAM (manteniendo el estado del grafo, los objetos de LangChain y el contexto de los documentos).

Si permites 20 peticiones concurrentes, necesitas un colchón de RAM de ~1 GB por Pod solo para el tráfico vivo, más la memoria base.

Si quieres subir el límite a 40 peticiones por instancia, debes subir el límite de memoria del Pod en tu YAML a 3Gi (3 GB).

💡 La regla de oro en Kubernetes: Es mejor escalar horizontalmente que verticalmente. En lugar de forzar a un solo Pod de FastAPI a manejar 50 peticiones concurrentes (subiendo su límite interno), es más eficiente que el Horizontal Pod Autoscaler (HPA) levante 4 Pods que manejen 12 peticiones cada uno. Esto distribuye el riesgo de fallos.

5. ¿Qué más se podría analizar? (Siguientes Pasos)
Con los datos que ya estás recolectando, puedes cruzar información para descubrir cosas fascinantes:

Tasa de Generación (Tokens por Segundo):

Cómo: Toma el Total Tokens de LangSmith y divídelo por (Total Chat Time - TTFT).

Para qué: Esto te dirá si, bajo estrés, la API de Google/OpenAI te está penalizando o ralentizando la entrega de tokens (Rate Limiting de su lado).

Latencia Neta de la Base Vectorial:

Cómo: En LangSmith, entra a uno de los Runs de estrés y busca solo el nodo knowledge_base_retriever. Mira cuánto tardó ese paso exacto.

Para qué: Si ves que el Retriever tarda 0.5s con 1 usuario pero tarda 6s con 100 usuarios, el cuello de botella no es tu RAM, ¡es tu proveedor de base de datos vectorial (Pinecone/Weaviate)!

Métricas de Celery (Lag de la Cola):

Cómo: Tienes el contenedor celery-exporter corriendo en tu clúster. Si lo conectas a un Prometheus/Grafana, puedes ver el "Queue Length" (tamaño de la fila).

Para qué: Si la cola subió a 50 PDFs y tardó 10 minutos en vaciarse, sabes que necesitas ajustar KEDA para que escale los workers mucho más agresivamente ante picos de documentos.

Análisis del Golden Dataset (Calidad vs Estrés):

Cómo: Cruzar las respuestas que dio BMO a las 136 preguntas de Locust contra tu "expected_answer" del Golden Dataset usando LangSmith Evaluators (LLM-as-a-judge).

Para qué: A veces, bajo mucho estrés, si el LLM se queda sin tokens o contexto por configuraciones de concurrencia, empieza a alucinar. Debes asegurar que la precisión de la respuesta de BMO a las 15:00 hs (con carga 0) sea igual de buena que a las 15:16 hs (con 100 usuarios atacando).