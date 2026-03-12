# workers/kafka_producer_test.py
import json
import uuid
import time
from confluent_kafka import Producer
from src.core.config import settings

KAFKA="localhost:9092"


def delivery_report(err, msg):
    """ Callback llamado cuando el mensaje es entregado o falla. """
    if err is not None:
        print(f'Entrega fallida: {err}')
    else:
        print(f'Mensaje entregado a {msg.topic()} [{msg.partition()}]')

def simulate_drive_event(filename: str, user_id: str, content: str = "Simulated content from Drive"):
    p = Producer({"bootstrap.servers": KAFKA})

    topic = settings.KAFKA_RAW_DOCUMENTS_TOPIC
    
    # El evento que simula el conector de Drive
    event = {
        "doc_id": str(uuid.uuid4()),
        "filename": filename,
        "user_id": user_id,
        "content": content,
        "metadata": {
            "source": "google_drive",
            "drive_id": f"drive_{uuid.uuid4().hex[:8]}"
        }
    }

    print(f"Produciendo evento para {filename}...")
    
    # Particionamos por user_id para mantener el orden por usuario
    p.produce(
        topic, 
        key=user_id, 
        value=json.dumps(event), 
        callback=delivery_report
    )

    # Flush para asegurar que se envie antes de salir
    p.flush()

if __name__ == "__main__":
    simulate_drive_event("manual_test_drive.txt", "user_1")
    time.sleep(1)
    simulate_drive_event("architecture_v2.pdf", "user_1", content="Complex architecture PDF content simulation")
