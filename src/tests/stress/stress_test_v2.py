from locust import HttpUser, task, between, events
import os
import uuid
import random
from datetime import datetime
from dotenv import load_dotenv

# Asegurar que el path incluya la raíz para importar GOLDEN_DATASET
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from src.evals.golden_dataset_v2 import GOLDEN_DATASET

load_dotenv(override=True)
TEST_USER_ID = "locust_tester"

def generate_heavy_unique_text():
    """Genera un texto pesado y único para evitar deduplicación."""
    paragraphs = [
        "El procesamiento de lenguaje natural y las bases de datos vectoriales permiten la recuperación semántica avanzada. ",
        "Durante las pruebas de carga, es imperativo asegurar que el tamaño del chunk y el overlap se respeten para no perder el contexto. ",
        "La latencia de ingesta depende en gran medida de la capacidad del broker de Kafka y la concurrencia de los workers de Celery. ",
        "El ruteo inteligente basado en la complejidad de la consulta reduce significativamente los costos operativos. ",
        "El uso de bases de datos relacionales robustas asegura que los estados de los procesos no sufran condiciones de carrera. "
    ]
    unique_id = uuid.uuid4().hex
    content = f"# Documento de Prueba de Estrés: {unique_id}\n\n"
    for _ in range(50): 
        content += random.choice(paragraphs)
    return content

class BMOStressUserV2(HttpUser):
    wait_time = between(1, 5)
    
    def on_start(self):
        """Inicializa datos para el usuario."""
        self.user_id = TEST_USER_ID
        self.thread_id = str(uuid.uuid4())
        self.headers = {
            "Content-Type": "application/json",
            "X-Stress-Test": "true"
        }
        # Extraer queries reales del Golden Dataset
        self.golden_queries = [entry["eval_query"] for entry in GOLDEN_DATASET]

    @task(10)
    def golden_dataset_query(self):
        """Consulta basada en el Golden Dataset."""
        query = random.choice(self.golden_queries)
        payload = {
            "message": query,
            "thread_id": self.thread_id,
            "user_info": {"user_id": self.user_id, "name": "StressTester"},
            "prompt_version": os.getenv("PROMPT_VERSION", "rag_v4")
        }
        self.client.post("/api/ask/stream", json=payload, headers=self.headers)

    @task(3)
    def web_search_only(self):
        """Búsqueda Web exclusiva."""
        payload = {
            "message": "¿Cuál es el precio actual de Bitcoin y qué dicen las últimas noticias?",
            "thread_id": self.thread_id,
            "user_info": {"user_id": self.user_id, "name": "StressTester"},
            "prompt_version": os.getenv("PROMPT_VERSION", "rag_v4")
        }
        self.client.post("/api/ask/stream", json=payload, headers=self.headers)

    @task(1)
    def ultra_complex_task(self):
        """Análisis complejo combinando información de múltiples notas."""
        payload = {
            "message": "Compará mis notas sobre KEDA con las de la auditoría de Kafka y haceme una tabla de riesgos, luego guarda ese analisis en la base de conocimineto.",
            "thread_id": self.thread_id,
            "user_info": {"user_id": self.user_id, "name": "StressTester"},
            "prompt_version": os.getenv("PROMPT_VERSION", "rag_v4")
        }
        self.client.post("/api/ask/stream", json=payload, headers=self.headers)

    @task(2)
    def upload_heavy_document(self):
        """Simula la subida de un documento pesado (esto genera carga en Redis/Celery/S3)."""
        heavy_content = generate_heavy_unique_text().encode('utf-8')
        doc_name = f"stress_doc_{uuid.uuid4().hex[:8]}.txt"
        
        files = {
            'file': (doc_name, heavy_content, 'text/plain')
        }
        data = {
            'user_id': self.user_id,
            'document_date': datetime.now().strftime("%Y-%m-%d")
        }
        self.client.post("/api/ingest", files=files, data=data, headers={"X-Stress-Test": "true"})
