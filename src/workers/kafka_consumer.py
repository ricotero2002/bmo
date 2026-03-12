# workers/kafka_consumer.py (Phase 3)
import json
import uuid
import logging
import asyncio
from datetime import datetime, timezone
from confluent_kafka import Consumer, KafkaError, KafkaException, Producer
from src.core.config import settings
from src.service.orchestrator import IngestionOrchestrator

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MAIN_TOPIC = settings.KAFKA_RAW_DOCUMENTS_TOPIC
DLT_TOPIC  = settings.KAFKA_DLT_TOPIC  # Dead Letter Topic
MAX_CONSUMER_RETRIES = 3

consumer = Consumer({
    "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
    "group.id": "document-ingestor",
    "enable.auto.commit": False,
    "auto.offset.reset": "earliest",
    "max.poll.interval.ms": 300000,
    "session.timeout.ms": 30000,
    "message.max.bytes": 104857600,
    "fetch.message.max.bytes": 104857600,
})

producer = Producer({
    "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
    "message.max.bytes": 104857600
})
orchestrator = IngestionOrchestrator()

consumer.subscribe([MAIN_TOPIC])

async def run_consumer():
    logger.info(f"Consumidor Kafka iniciado. Escuchando tópico: {MAIN_TOPIC}")
    try:
        while True:
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError.PARTITION_EOF:
                    continue  # end of partition, not an error
                raise KafkaException(msg.error())

            headers = dict(msg.headers() or [])
            retry_raw = headers.get("retry-count", b"0")
            retry_count = int(retry_raw.decode() if isinstance(retry_raw, bytes) else retry_raw)

            try:
                # El payload debería contener doc_id (opcional), filename, y opcionalmente user_id, content/path
                payload = json.loads(msg.value())
                
                doc_id = uuid.UUID(payload.get("doc_id")) if payload.get("doc_id") else uuid.uuid4()
                filename = payload.get("filename", "unknown_file")
                user_id = payload.get("user_id")
                content = payload.get("content")
                object_name = payload.get("object_name")
                
                # Orquestamos la ingesta
                await orchestrator.orchestrate_ingestion(
                    doc_id=doc_id,
                    filename=filename,
                    content=content.encode() if isinstance(content, str) else content,
                    user_id=user_id,
                    object_name=object_name,
                    metadata=payload.get("metadata")
                )
                
                # Commit en Kafka solo después de que el orchestrator (y por ende RabbitMQ) confirme
                consumer.commit(message=msg)
                logger.info(f"Mensaje procesado y commiteado en Kafka: {doc_id}")

            except Exception as exc:
                logger.error(f"Error procesando mensaje de Kafka: {exc}")
                if retry_count < MAX_CONSUMER_RETRIES:
                    # Re-publicar al mismo tópico con contador incrementado
                    producer.produce(
                        MAIN_TOPIC,
                        key=msg.key(),
                        value=msg.value(),
                        headers={"retry-count": str(retry_count + 1).encode()},
                    )
                    producer.flush()
                else:
                    # Agotados los reintentos -> DLT
                    producer.produce(
                        DLT_TOPIC,
                        key=msg.key(),
                        value=msg.value(),
                        headers={
                            "original-topic": MAIN_TOPIC.encode(),
                            "error": str(exc).encode(),
                            "failed-at": datetime.now(timezone.utc).isoformat().encode(),
                        },
                    )
                    producer.flush()
                    logger.error(f"Mensaje enviado a DLT ({DLT_TOPIC}) después de {retry_count} reintentos")

                # Movemos el offset de todos modos para no quedar bloqueados en un mensaje roto
                consumer.commit(message=msg)

    finally:
        consumer.close()

if __name__ == "__main__":
    asyncio.run(run_consumer())