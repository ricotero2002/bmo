import os
import logging
import certifi
from src.core.config import settings
from src.providers.messaging.openssl_runtime import configure_openssl_runtime

logger = logging.getLogger(__name__)


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
        openssl_runtime = configure_openssl_runtime()
        logger.info(
            "Kafka OpenSSL runtime configurado",
            extra={
                "openssl_conf": openssl_runtime.get("openssl_conf"),
                "openssl_modules": openssl_runtime.get("openssl_modules"),
                "provider": openssl_runtime.get("kafka_ssl_provider"),
            },
        )

        username = os.getenv("KAFKA_SASL_USERNAME")
        password = os.getenv("KAFKA_SASL_PASSWORD")
        if not username or not password:
            raise ValueError("Kafka production config requires KAFKA_SASL_USERNAME and KAFKA_SASL_PASSWORD")

        base.update({
            "security.protocol": "SASL_SSL",
            "sasl.mechanisms": "SCRAM-SHA-256",
            "sasl.username": username,
            "sasl.password": password,
        })

        ca_location = os.getenv("KAFKA_SSL_CA_LOCATION")
        if ca_location:
            ca_location = os.path.abspath(ca_location)
            if os.path.exists(ca_location):
                base["ssl.ca.location"] = ca_location
            else:
                logger.warning(
                    "KAFKA_SSL_CA_LOCATION no existe en %s, usando certifi como fallback",
                    ca_location,
                )
                base["ssl.ca.location"] = certifi.where()
        else:
            base["ssl.ca.location"] = certifi.where()

        if os.getenv("KAFKA_SSL_DEBUG", "").lower() in {"1", "true", "yes"}:
            base["debug"] = "security,broker"
            base["ssl.endpoint.identification.algorithm"] = "none"

    if extra:
        base.update(extra)

    return base
