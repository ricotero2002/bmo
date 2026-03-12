from celery import Celery
import os
from kombu import Queue, Exchange
from src.core.config import settings

# Initialize Celery app
celery_app = Celery(
    'bmo',
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["src.workers.tasks"]
)

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
    worker_prefetch_multiplier=settings.worker_prefetch_multiplier,
    task_acks_late=True,
    worker_max_tasks_per_child=settings.worker_max_tasks_per_child,
    
    # Timeouts
    task_soft_time_limit=300,
    task_time_limit=600,
    
    # Resultados
    result_expires=3600,
    result_extended=True,
    
    # Retry policy
    task_default_retry_delay=60,
    task_max_retries=3,
    
    # Queues
    task_default_queue="default",
    task_queues=(
        Queue("default", Exchange("default"), routing_key="default"),
        Queue("ai_processing", Exchange("ai_processing"), routing_key="ai.#"),
        # Nueva cola de ingesta con DLX (Dead Letter Exchange)
        Queue(
            "ingest_q",
            Exchange("ingest_q", type="direct", durable=True),
            routing_key="ingest_q",
            durable=True,
            queue_arguments={
                "x-message-ttl": 86400000,  # 24h
                "x-dead-letter-exchange": "ingest_dlx",
                "x-dead-letter-routing-key": "ingest_dlq",
            }
        ),
        # Cola para mensajes fallidos (Dead Letter Queue)
        Queue(
            "ingest_dlq",
            Exchange("ingest_dlx", type="direct", durable=True),
            routing_key="ingest_dlq",
            durable=True,
        ),
    ),
    
    # Routing
    task_routes={
        "src.workers.tasks.process_document_task": {"queue": "ingest_q"},
    },
    
    # Reliability
    task_acks_late=True,
    worker_reject_on_worker_lost=True,
    
    # Monitoring
    worker_send_task_events=True,
    task_send_sent_event=True,
)

# Periodic tasks
celery_app.conf.beat_schedule = {
    "cleanup-expired-cache": {
        "task": "src.workers.tasks.cleanup_expired_cache",
        "schedule": 3600.0,
    },
}

if __name__ == '__main__':
    celery_app.start()


