import logging
from typing import Optional
from confluent_kafka import Producer
from src.providers.messaging.kafka_config import build_kafka_conf

logger = logging.getLogger(__name__)


class KafkaProducerWrapper:
    """
    Singleton thread-safe que encapsula confluent_kafka.Producer.

    Diseñado para ser usado en contextos de baja frecuencia (tools del agente),
    donde se requiere publicar mensajes de forma fire-and-forget sin bloquear
    la respuesta al usuario.

    Uso:
        producer = KafkaProducerWrapper.get_instance()
        producer.produce(topic="raw-documents", key="doc_id", value=json.dumps(payload))
    """
    _instance: Optional["KafkaProducerWrapper"] = None

    def __init__(self):
        # Importamos la configuración centralizada que ya tiene el fix de OpenSSL
        from src.providers.messaging.kafka_config import build_kafka_conf
        
        conf = build_kafka_conf()
        self._producer = Producer(conf)
        logger.info(
            "KafkaProducerWrapper inicializado. "
            f"Brokers: {conf.get('bootstrap.servers')}"
        )

    @classmethod
    def get_instance(cls) -> "KafkaProducerWrapper":
        """Retorna la instancia singleton, creándola si no existe."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Resetea el singleton (útil en tests)."""
        cls._instance = None

    def produce(self, topic: str, key: str, value: str) -> None:
        """
        Publica un mensaje en Kafka de forma asíncrona (fire-and-forget).

        Args:
            topic:  Nombre del tópico Kafka destino.
            key:    Clave de particionamiento (ej: doc_id o user_id).
            value:  Payload JSON como string.
        """
        self._producer.produce(
            topic,
            key=key.encode("utf-8"),
            value=value.encode("utf-8"),
            callback=self._delivery_report,
        )
        # poll(0) dispara los callbacks de entrega pendientes sin bloquear
        self._producer.poll(0)

    def flush(self, timeout: float = 5.0) -> None:
        """
        Bloquea hasta que todos los mensajes pendientes sean entregados.
        Útil en shutdown o en tests.

        Args:
            timeout: Segundos máximos de espera.
        """
        self._producer.flush(timeout)

    @staticmethod
    def _delivery_report(err, msg) -> None:
        """Callback de entrega invocado por confluent_kafka tras confirmar o fallar."""
        if err is not None:
            logger.error(
                f"KafkaProducer: entrega fallida para '{msg.topic()}' "
                f"[partition {msg.partition()}]: {err}"
            )
        else:
            logger.info(
                f"KafkaProducer: mensaje entregado a '{msg.topic()}' "
                f"[partition {msg.partition()}, offset {msg.offset()}]"
            )
