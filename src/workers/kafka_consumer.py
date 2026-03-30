# workers/kafka_consumer.py (Phase 3)
import json
import uuid
import logging
import asyncio
from datetime import datetime, timezone
from confluent_kafka import Consumer, KafkaError, KafkaException, Producer
import certifi
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
GROUP_ID = os.getenv("KAFKA_GROUP_ID", "document-ingestor-v3")

orchestrator = IngestionOrchestrator()


def _build_kafka_conf(extra: dict = None) -> dict:
    """Construye la configuración de Kafka soportando local y Aiven (TLS/SASL)."""
    base = {
        "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
        "message.max.bytes": 104857600,
    }
    if settings.APP_ENV == "production":
        # Aiven Kafka: SASL_SSL + SCRAM-SHA-256
        # Variables: KAFKA_SASL_USERNAME, KAFKA_SASL_PASSWORD
        # Opcional: KAFKA_SSL_CA_LOCATION (ruta al ca.pem de Aiven)
        base.update({
            "security.protocol": "SASL_SSL",
            "sasl.mechanisms": "SCRAM-SHA-256",
            "sasl.username": os.getenv("KAFKA_SASL_USERNAME"),
            "sasl.password": os.getenv("KAFKA_SASL_PASSWORD"),
        })
        ca_location = os.getenv("KAFKA_SSL_CA_LOCATION")
        if ca_location:
            ca_location = os.path.abspath(ca_location)
            if os.path.exists(ca_location):
                base["ssl.ca.location"] = ca_location
            else:
                base["ssl.ca.location"] = certifi.where()
        else:
            base["ssl.ca.location"] = certifi.where()
    if extra:
        base.update(extra)
    return base


async def run_consumer():
    # Inicialización diferida para asegurar settings cargados y OTel listo
    logger.info(f"Conectando a Kafka: {settings.KAFKA_BOOTSTRAP_SERVERS} (env={settings.APP_ENV})")

    conf = _build_kafka_conf({
        "group.id": GROUP_ID,
        "enable.auto.commit": False,
        "auto.offset.reset": "earliest",
        "max.poll.interval.ms": 300000,
        "session.timeout.ms": 30000,
        "fetch.message.max.bytes": 104857600,
        "metadata.max.age.ms": 5000,
        "topic.metadata.refresh.interval.ms": 5000,
    })

    consumer = Consumer(conf)
    producer = Producer(_build_kafka_conf())

    consumer.subscribe([MAIN_TOPIC])
    logger.info(f"Consumidor Kafka iniciado. Escuchando tópico: {MAIN_TOPIC}")
    try:
        while True:
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
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