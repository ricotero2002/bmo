# Fase 3: Streaming y Orquestación

## Estado Actual de la Arquitectura
**¿Lo que tengo ahora es la API?**
Sí, actualmente el sistema tiene dos "puertas de entrada":
1.  **API REST (FastAPI)**: Atiende subidas manuales vía `/ingest`.
2.  **Kafka Consumer**: Atiende eventos automáticos vía el tópico `raw-documents`.

Ambas puertas usan el `IngestionOrchestrator`, por lo que el proceso posterior (guardar en Postgres, subir a MinIO y procesar con Celery) es idéntico y robusto.

## El Productor Real (Fase 4)
Lo que falta para tener un flujo "real-time" completo es el conector que vigila la fuente externa y genera los eventos en Kafka.

### Concepto de Productor para Google Drive
Este sería un servicio independiente que consulta la API de Google y produce mensajes:

```python
# productores/drive_connector.py
import base64
from confluent_kafka import Producer

def drive_to_kafka():
    p = Producer({'bootstrap.servers': 'localhost:9092'})
    
    # Simulación de polling a Drive
    files = drive_api.get_changed_files() 
    
    for file in files:
        content = drive_api.download(file.id)
        payload = {
            "doc_id": str(uuid.uuid4()),
            "filename": file.name,
            "user_id": file.owner_id,
            "content": base64.b64encode(content).decode('utf-8'),
            "metadata": {"source": "google_drive", "drive_id": file.id}
        }
        
        p.produce("raw-documents", key=file.owner_id, value=json.dumps(payload))
    p.flush()
```

## Monitoreo de Kafka
Para vigilar que todo funcione correctamente:
- **UI**: Accede a `localhost:8080` (Kafka UI).
- **Consumo**: Vigila el "Consumer Lag" (la diferencia entre lo producido y lo procesado).
- **DLT**: Si hay mensajes en `raw-documents-dlt`, algo está fallando en el formato o la orquestación inicial.

