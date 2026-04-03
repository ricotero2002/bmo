import json
import uuid
import logging
import re
from datetime import datetime, timezone

from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

from src.core.config import settings
from src.providers.messaging.kafka_producer import KafkaProducerWrapper

logger = logging.getLogger(__name__)


def _slugify(title: str) -> str:
    """Convierte un título en un string seguro para usar como nombre de archivo."""
    slug = title.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "_", slug)
    return slug[:60]  # Limita la longitud para evitar nombres excesivamente largos


@tool
def save_note_to_knowledge_base(
    title: str,
    content: str,
    doc_type: str = "general",
    config: RunnableConfig = None,
) -> str:
    """
    Guarda una nueva idea, resumen o plan en la base de conocimientos permanente.
    Úsala cuando el usuario te pida guardar algo, o cuando generes un resumen útil
    que deba ser recordado a largo plazo.
    La nota se procesa en segundo plano y estará disponible para búsquedas en minutos.
    """
    user_id = config.get("configurable", {}).get("user_id") if config else None
    logger.info(f"save_note_to_knowledge_base: publicando nota '{title}' (user={user_id})")

    try:
        # 1. Formatear el contenido como Markdown
        formatted_content = f"# {title}\n\n{content}"

        # 2. Construir un filename descriptivo y único
        slug = _slugify(title)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        doc_id = str(uuid.uuid4())
        filename = f"agent_notes/{slug}_{timestamp}.md"

        # 3. Payload compatible con el schema del kafka_consumer.py:
        #    doc_id, filename, user_id, content (str), metadata
        payload = {
            "doc_id": doc_id,
            "filename": filename,
            "user_id": user_id,
            "content": formatted_content,  # El consumer lo encodea a bytes si es str
            "metadata": {
                "source": filename,
                "doc_type": doc_type,
                "title": title,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "origin": "bmo_agent_generated",
            },
        }

        # 4. Publicar en Kafka — fire-and-forget
        producer = KafkaProducerWrapper.get_instance()
        producer.produce(
            topic=settings.KAFKA_RAW_DOCUMENTS_TOPIC,
            key=doc_id,
            value=json.dumps(payload, ensure_ascii=False),
        )

        logger.info(f"Nota '{title}' publicada en Kafka con doc_id={doc_id}")
        return (
            f"Nota '{title}' guardada exitosamente y procesándose en segundo plano. "
            f"(ID: {doc_id})"
        )

    except Exception as e:
        logger.error(f"Error al publicar nota en Kafka: {e}")
        return (
            "Hubo un error de comunicación al intentar guardar la nota. "
            "Por favor intenta nuevamente."
        )
