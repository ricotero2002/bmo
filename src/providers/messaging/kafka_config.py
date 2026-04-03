import os
import certifi
from src.core.config import settings


def build_kafka_conf(extra: dict = None) -> dict:
    """
    Construye la configuración base de Kafka soportando entornos local y Aiven (TLS/SASL).

    En local: conexión plana a localhost:9092.
    En producción: SASL_SSL + SCRAM-SHA-256 contra Aiven Kafka.

    Variables de entorno requeridas en producción:
        KAFKA_SASL_USERNAME     — usuario SASL de Aiven
        KAFKA_SASL_PASSWORD     — contraseña SASL de Aiven
        KAFKA_SSL_CA_LOCATION   — ruta al ca.pem de Aiven (opcional, cae en certifi)

    Args:
        extra: dict adicional de opciones confluent_kafka para sobreescribir o extender.

    Returns:
        dict de configuración para confluent_kafka.Producer / Consumer.
    """
    base = {
        "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
        "message.max.bytes": 31457280 ,  # 30 MB
    }

    if settings.APP_ENV == "production":
        base.update({
            "security.protocol": "SASL_SSL",
            "sasl.mechanisms": "SCRAM-SHA-256",
            "sasl.username": os.getenv("KAFKA_SASL_USERNAME"),
            "sasl.password": os.getenv("KAFKA_SASL_PASSWORD"),
        })

        ca_location = os.getenv("KAFKA_SSL_CA_LOCATION")
        if ca_location:
            ca_location = os.path.abspath(ca_location)
            base["ssl.ca.location"] = ca_location if os.path.exists(ca_location) else certifi.where()
        else:
            base["ssl.ca.location"] = certifi.where()

    if extra:
        base.update(extra)

    return base
