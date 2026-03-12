# workers/kafka_producer_large_file_test.py
import json
import uuid
import time
import os
import io
from confluent_kafka import Producer
from src.core.config import settings
from src.providers.storage.factory import StorageFactory

def delivery_report(err, msg):
    if err is not None:
        print(f'Entrega fallida: {err}')
    else:
        print(f'Mensaje entregado a {msg.topic()} [{msg.partition()}]')

def test_large_file_ingestion_direct(size_mb: int = 100):
    user_id = "user_large_test"
    # USAMOS UN ID FIJO PARA PROBAR IDEMPOTENCIA
    doc_id = uuid.UUID("baaaaaad-f00d-4000-8000-000000000000")
    filename = f"heavy_direct_{size_mb}mb.txt"
    
    print(f"--- Iniciando prueba de archivo pesado DIRECTO ({size_mb} MB) ---")
    
    # 1. Generar contenido pesado
    print(f"Generando {size_mb} MB para el payload...")
    large_data = "X" * (size_mb * 1024 * 1024)
    
    # 2. Configurar Productor con límites aumentados
    p = Producer({
        "bootstrap.servers": "localhost:9092",
        "message.max.bytes": 104857600, # 100MB
    })
    
    topic = settings.KAFKA_RAW_DOCUMENTS_TOPIC
    
    event = {
        "doc_id": str(doc_id),
        "filename": filename,
        "user_id": user_id,
        "content": large_data, # Mandamos el contenido de una
        "metadata": {
            "source": "kafka_direct_heavy",
            "size_mb": size_mb
        }
    }
    
    print(f"Enviando {size_mb}MB directamente a Kafka...")
    try:
        p.produce(
            topic, 
            key=user_id, 
            value=json.dumps(event), 
            callback=delivery_report
        )
        p.flush()
        print(f"--- Evento enviado. ID Fijo: {doc_id} ---")
    except Exception as e:
        print(f"Error produciendo mensaje pesado: {e}")

if __name__ == "__main__":
    # Probamos con 100MB directos (límite configurado en broker)
    test_large_file_ingestion_direct(99)
