¡Entendido! Esto cambia por completo la perspectiva del análisis. Si ambos tests fueron con **30 usuarios concurrentes**, estamos ante una **comparativa perfecta (manzanas con manzanas)** entre tu antigua arquitectura (Fase 7: Advanced RAG) y tu nueva arquitectura (Fase 8: Agente Multi-Herramienta con Planificador y Memoria).

Aquí tienes el análisis corregido. Las conclusiones sobre el rendimiento revelan exactamente el "costo de la inteligencia".

### 1. Comparativa Real: Arquitectura Anterior vs. Nueva (Ambas a 30 Usuarios)

| Métrica | Fase 7 (Advanced RAG) | Fase 8 (Agentic Multi-Tool) | Análisis del Cambio |
| :--- | :--- | :--- | :--- |
| **Fallos (Fails)** | 0% | 0% | **Excelente**. El sistema sigue siendo una roca. El Pool de Conexiones de Postgres absorbió la carga perfectamente. |
| **TTFT (Mediana)** | 4.6 segundos | 9.3 segundos | **El "Impuesto" del Planificador**. El TTFT se duplicó porque antes BMO buscaba y respondía directo. Ahora, BMO debe invocar a un LLM (`task_planner`) para crear un plan, y ejecutar herramientas (como `web_search`) *antes* de emitir el primer token. |
| **Tiempo de Chat** | 48 segundos | 102 a 257 segundos | **Profundidad Cognitiva**. Las tareas ahora son *Multi-Hop*. BMO evalúa documentos, busca en la web, resume la corrida y audita si terminó la tarea. Todo ese bucle en LangGraph toma 2x a 5x más tiempo. |
| **Tokens Procesados** | 2.33 Millones | 3.23 Millones | **Mayor Verbocidad Interna**. Esos ~900k tokens extra son el consumo \"invisible\" de los nodos de validación (Graders) y el Task Planner. |
| **Costo Total** | $0.247 USD | $2.13 USD | **Multiplicación de llamadas**. Cada interacción ahora dispara entre 3 y 6 llamadas al LLM (Plan -> Tool -> Grade -> Respond -> Summarize). |
| **Ingesta (Mediana)** | 3.6 segundos | 3.6 segundos | **Aislamiento Perfecto**. Tu worker de Celery sigue intacto y no se ve afectado por el estrés del LLM. |

---

### 2. Análisis de Cuellos de Botella (CPU al 167%)

En los logs vimos que tu HPA disparó la alerta: `api-hpa cpu: 167%/60%`. 
Si esto pasó con solo 30 usuarios, significa que **tu CPU está sufriendo "Context Switching" severo**. 

FastAPI es asíncrono, lo que significa que acepta a los 30 usuarios al mismo tiempo. Al procesar 30 grafos de LangGraph en paralelo dentro del mismo contenedor, la CPU salta de una tarea a otra tan rápido que se satura, enlenteciendo el procesamiento de *todos* a la vez.

#### A. ¿Debería aumentar el Semáforo de FastAPI a más de 30?
**Respuesta Definitiva: NO. De hecho, deberías BAJARLO a 15.**
* **La Lógica Contraintuitiva:** Si tienes 30 usuarios y un semáforo de 30, todos entran a pelear por la misma CPU. Como resultado, la CPU llega al 167% y **todos** tardan 100 segundos en recibir su respuesta.
* **Si bajas el semáforo a 15:** Los primeros 15 usuarios usarán la CPU al 80%, terminando su chat en ~40 segundos. Los otros 15 esperarán en la fila sin consumir CPU, y luego entrarán y tardarán otros 40 segundos. Al final, *el tiempo promedio bajará drásticamente* y la CPU nunca llegará al colapso del 167%.

#### B. ¿Debería aumentar la cantidad máxima de workers de Celery a 2?
**Respuesta Definitiva: SÍ.**
* **La Lógica:** Vimos que la métrica `keda-hpa-celery-worker-scaler` llegó a **`28/5 (avg)`**. Esto significa que había 28 documentos en la fila de RabbitMQ esperando a ser procesados.
* Al subir a `--concurrency=2` en el contenedor de Celery (y sabiendo que tienes 768Mi de límite de RAM que aguantan perfecto), matarás esa cola de 28 documentos en la mitad del tiempo.

### 💡 Plan de Acción de Infraestructura

1. **En `endpoints.py`:** Cambia `llm_semaphore = asyncio.Semaphore(15)` (o 20 como máximo). No dejes que 30 grafos de LangGraph corran simultáneamente en el mismo Pod.
2. **En `api-hpa.yaml`:** Sube el `maxReplicas` a **3 o 4**. Deja que Kubernetes resuelva la carga levantando más Pods de FastAPI, en lugar de sofocar a un solo Pod.
3. **En `apps-deployment.yaml`:** Sube a `--concurrency=2` en el comando de Celery.

**Conclusión del Test:** Arquitectónicamente, el test es un triunfo absoluto. Has construido un sistema Agéntico complejo que no se rompe bajo presión. Los tiempos más altos son simplemente la consecuencia matemática de hacer que el modelo \"piense\" mucho más antes de hablar.