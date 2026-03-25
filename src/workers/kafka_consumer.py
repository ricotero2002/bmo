# workers/kafka_consumer.py (Phase 3)
import json
import uuid
import logging
import asyncio
from datetime import datetime, timezone
from confluent_kafka import Consumer, KafkaError, KafkaException, Producer
from src.core.config import settings
from src.service.orchestrator import IngestionOrchestrator
import os
# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- OpenTelemetry Setup ---
from src.core.telemetry import metrics_registry, TelemetryCallbackHandler
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

otel_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
if otel_endpoint:
    # Traces
    tp = TracerProvider()
    tp.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=otel_endpoint, insecure=True)))
    trace.set_tracer_provider(tp)
    # Metrics
    mr = PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=otel_endpoint, insecure=True))
    mp = MeterProvider(metric_readers=[mr])
    metrics.set_meter_provider(mp)

tracer = trace.get_tracer(__name__)

MAIN_TOPIC = settings.KAFKA_RAW_DOCUMENTS_TOPIC
DLT_TOPIC  = settings.KAFKA_DLT_TOPIC  # Dead Letter Topic
MAX_CONSUMER_RETRIES = 3

orchestrator = IngestionOrchestrator()

async def run_consumer():
    # Inicialización diferida para asegurar settings cargados y OTel listo
    logger.info(f"Conectando a Kafka: {settings.KAFKA_BOOTSTRAP_SERVERS}")
    
    conf = {
        "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
        "group.id": "document-ingestor-v3", # CAMBIAMOS EL GRUPO PARA RESETEAR ESTADO
        "enable.auto.commit": False,
        "auto.offset.reset": "earliest",
        "max.poll.interval.ms": 300000,
        "session.timeout.ms": 30000,
        "message.max.bytes": 104857600,
        "fetch.message.max.bytes": 104857600,
        "metadata.max.age.ms": 5000, # FORZAR REFRESH DE METADATOS CADA 5 SEG SI HAY ERRORES
        "topic.metadata.refresh.interval.ms": 5000,
        "debug": "broker"
    }
    
    consumer = Consumer(conf)
    producer = Producer({
        "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
        "message.max.bytes": 104857600
    })

    consumer.subscribe([MAIN_TOPIC])
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

            with tracer.start_as_current_span("kafka_process_message", attributes={"topic": MAIN_TOPIC}) as span:
                try:
                    # El payload debería contener doc_id (opcional), filename, y opcionalmente user_id, content/path
                    payload = json.loads(msg.value())
                    
                    doc_id = uuid.UUID(payload.get("doc_id")) if payload.get("doc_id") else uuid.uuid4()
                    filename = payload.get("filename", "unknown_file")
                    user_id = payload.get("user_id")
                    content = payload.get("content")
                    object_name = payload.get("object_name")
                    
                    span.set_attribute("doc_id", str(doc_id))
                    span.set_attribute("filename", filename)

                    # Orquestamos la ingesta
                    await orchestrator.orchestrate_ingestion(
                        doc_id=doc_id,
                        filename=filename,
                        content=content.encode() if isinstance(content, str) else content,
                        user_id=user_id,
                        object_name=object_name,
                        metadata=payload.get("metadata")
                    )
                    
                    # Métrica de negocio
                    metrics_registry.docs_processed.add(1, {"status": "kafka_success", "source": "kafka"})

                except Exception as exc:
                    span.record_exception(exc)
                    logger.error(f"Error procesando mensaje de Kafka: {exc}")
                    metrics_registry.docs_processed.add(1, {"status": "kafka_error", "source": "kafka"})
                    if retry_count < MAX_CONSUMER_RETRIES:
                        # Re-publicar al mismo tópico con contador incrementado
                        producer.produce(
                            MAIN_TOPIC,
                            key=msg.key(),
                            value=msg.value(),
                            headers={"retry-count": str(retry_count + 1).encode()},
                        )
                        producer.flush()
                        logger.warning(f"Error procesando mensaje. Reintentando ({retry_count + 1}/{MAX_CONSUMER_RETRIES})")
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

                # Movemos el offset de todos modos para no quedar bloqueados
                consumer.commit(message=msg)

    finally:
        consumer.close()

if __name__ == "__main__":
    asyncio.run(run_consumer())