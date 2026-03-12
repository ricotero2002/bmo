# Configuración de Celery
celery_app.conf.update(
    # Serialización
    task_serializer=settings.celery_task_serializer,
    result_serializer=settings.celery_result_serializer,
    accept_content=settings.celery_accept_content,
    
    # Timezone
    timezone=settings.celery_timezone,
    enable_utc=settings.celery_enable_utc,
    
    # Optimización para tareas de IA pesadas
    worker_prefetch_multiplier=settings.worker_prefetch_multiplier,  # 1 tarea a la vez
    task_acks_late=True,  # Confirmar después de completar
    worker_max_tasks_per_child=settings.worker_max_tasks_per_child,  # Reiniciar después de N tareas
    
    # Timeouts
    task_soft_time_limit=300,  # 5 minutos soft limit
    task_time_limit=600,  # 10 minutos hard limit
    
    # Resultados
    result_expires=3600,  # Los resultados expiran en 1 hora
    result_extended=True,
    
    # Retry policy
    task_default_retry_delay=60,  # Reintentar después de 1 minuto
    task_max_retries=3,
    
    # Queues
    task_default_queue="default",
    task_queues=(
        Queue("default", Exchange("default"), routing_key="default"),
        Queue("ai_processing", Exchange("ai_processing"), routing_key="ai.#"),
        Queue("kafka_events", Exchange("kafka_events"), routing_key="kafka.#"),
    ),
    
    # Routing
    task_routes={
        "celery_tasks.process_with_llm": {"queue": "ai_processing", "routing_key": "ai.llm"},
        "celery_tasks.process_kafka_event": {"queue": "kafka_events", "routing_key": "kafka.event"},
        "celery_tasks.generate_embedding": {"queue": "ai_processing", "routing_key": "ai.embedding"},
    },
    
    # Monitoring
    worker_send_task_events=True,
    task_send_sent_event=True,
)

1. Serialización (Formato de datos)
task_serializer / result_serializer: Define cómo se "empaquetan" los datos (usualmente json). El JSON es estándar y seguro, aunque menos eficiente que pickle para objetos complejos de Python.
accept_content: Una lista blanca de formatos permitidos (ej. ['json']). Es una medida de seguridad para que el worker no ejecute código malicioso serializado.
2. Timezone (Gestión del tiempo)
timezone: Define la zona horaria para tareas programadas (Celery Beat).
enable_utc: Obliga a usar UTC internamente. Es la mejor práctica para evitar errores de desfase horario entre servidores.
3. Optimización para IA (Carga Pesada)
worker_prefetch_multiplier: Si está en 1, el worker solo toma una tarea de la cola a la vez. Para IA (que consume mucha RAM/GPU), esto evita que un worker "acapare" tareas que no puede procesar simultáneamente, permitiendo que otros workers libres las tomen.
task_acks_late: Por defecto, Celery confirma la tarea apenas la recibe. Con True, solo confirma después de terminarla. Si el worker muere a mitad de un proceso de IA, la tarea vuelve a la cola para que otro la intente.
worker_max_tasks_per_child: Reinicia el proceso "hijo" del worker tras ejecutar N tareas. Es vital en IA para limpiar fugas de memoria (memory leaks) que suelen dejar librerías como PyTorch o TensorFlow.
4. Timeouts (Límites de tiempo)
task_soft_time_limit: Envía una excepción (SoftTimeLimitExceeded) a la tarea a los 5 min. Permite que tu código "limpie" lo que estaba haciendo antes de morir.
task_time_limit: El "botón de pánico". A los 10 min, mata el proceso a la fuerza. Evita tareas zombis que bloqueen recursos infinitamente.
5. Resultados
result_expires: Borra los resultados del backend (Redis/Database) tras 1 hora para no saturar el almacenamiento.
result_extended: Guarda metadatos extra (como parámetros de la tarea o nombre de la cola) en el backend de resultados. Útil para auditoría.
6. Retry Policy (Reintentos)
task_default_retry_delay: Tiempo de espera entre reintentos fallidos (60 seg).
task_max_retries: Cuántas veces se intentará la tarea antes de marcarla como "FAILURE".
7. Queues y Routing (Organización del tráfico)
task_queues: Define "carriles" separados.
ai_processing: Para tareas pesadas de GPU/CPU.
kafka_events: Para mensajería rápida.
task_routes: Es el mapa de tráfico. Manda funciones específicas a colas específicas automáticamente. Así, puedes tener workers potentes escuchando solo la cola de ai_processing y workers ligeros para el resto.
8. Monitoring (Visibilidad)
worker_send_task_events / task_send_sent_event: Habilita el envío de mensajes de estado constantes. Es lo que permite que herramientas como Flower te muestren gráficos en tiempo real de qué está pasando.


falta el tema de la cache que por ahora no lo voy a realizar.

Probar tests