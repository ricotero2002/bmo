import time
import json
import os
import uuid
import random
from datetime import datetime
from dotenv import load_dotenv
from locust import HttpUser, task, between, events

# Asegurar que el path incluya la raíz para importar GOLDEN_DATASET
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from src.evals.golden_dataset_v2 import GOLDEN_DATASET

load_dotenv(override=True)
TEST_USER_ID = "locust_tester"

def generate_heavy_unique_text():
    """
    Genera un texto pesado y 100% único en cada ejecución para 
    bypassear cualquier chequeo de duplicidad (hashes) en la ingesta.
    """
    paragraphs = [
        "El procesamiento de lenguaje natural y las bases de datos vectoriales permiten la recuperación semántica avanzada. ",
        "Durante las pruebas de carga, es imperativo asegurar que el tamaño del chunk y el overlap se respeten para no perder el contexto. ",
        "La latencia de ingesta depende en gran medida de la capacidad del broker de Kafka y la concurrencia de los workers de Celery. ",
        "El ruteo inteligente basado en la complejidad de la consulta reduce significativamente los costos operativos de la API del LLM. ",
        "El uso de bases de datos relacionales robustas como PostgreSQL asegura que los estados de los procesos no sufran condiciones de carrera. "
    ]
    
    # 1. Inyectamos un identificador único absoluto en el contenido
    unique_id = uuid.uuid4().hex
    content = f"# Documento de Prueba de Estrés: {unique_id}\n\n"
    
    # 2. Generamos unas 15-20 páginas de contenido barajando los párrafos
    for _ in range(50): 
        content += random.choice(paragraphs)
        if random.random() > 0.8: # Salto de línea aleatorio
            content += "\n"
            
    return content

class BMOStressUserV2(HttpUser):
    wait_time = between(2, 5)
    host = "http://localhost:8081"

    def on_start(self):
        """Inicializa datos para el usuario."""
        self.user_id = TEST_USER_ID
        self.headers = {
            "X-Stress-Test": "true"
        }
        # Extraer queries reales del Golden Dataset
        self.golden_queries = [entry["eval_query"] for entry in GOLDEN_DATASET]

    def _process_stream(self, name, payload):
        """Helper robusto para procesar el stream de forma idéntica a locustfile.py."""
        start_time = time.time()
        ttft_recorded = False

        with self.client.post("/api/ask/stream", json=payload, headers=self.headers, stream=True, catch_response=True, timeout=500) as response:
            if response.status_code == 200:
                try:
                    for line in response.iter_lines():
                        if line:
                            decoded_line = line.decode('utf-8')
                            
                            # Capturar TTFT
                            if not ttft_recorded and '"type": "token"' in decoded_line:
                                ttft = time.time() - start_time
                                events.request.fire(
                                    request_type="SSE",
                                    name=f"TTFT - {name}",
                                    response_time=ttft * 1000,
                                    response_length=0,
                                )
                                ttft_recorded = True

                            if "[DONE]" in decoded_line:
                                break
                    
                    total_time = time.time() - start_time
                    events.request.fire(
                        request_type="SSE",
                        name=f"Total Time - {name}",
                        response_time=total_time * 1000,
                        response_length=0,
                    )
                    response.success()
                except Exception as e:
                    response.failure(f"Stream interrupted in {name}: {str(e)}")
            else:
                response.failure(f"Error {response.status_code} in {name}: {response.text}")

    @task(10)
    def golden_dataset_query(self):
        """Consulta basada en el Golden Dataset."""
        thread_id = str(uuid.uuid4())
        query = random.choice(self.golden_queries)
        payload = {
            "message": query,
            "thread_id": thread_id,
            "user_info": {"user_id": self.user_id, "is_stress_test": True},
            "prompt_version": os.getenv("PROMPT_VERSION", "rag_v4")
        }
        self._process_stream("Golden Dataset Query", payload)

    @task(3)
    def web_search_only(self):
        """Búsqueda Web exclusiva."""
        thread_id = str(uuid.uuid4())
        payload = {
            "message": "¿Cual fue la formacion de boca vs u catolica el jueves 7 de abril?",
            "thread_id": thread_id,
            "user_info": {"user_id": self.user_id, "is_stress_test": True},
            "prompt_version": os.getenv("PROMPT_VERSION", "rag_v4")
        }
        self._process_stream("Web Search Only", payload)

    @task(1)
    def ultra_complex_task(self):
        """Análisis complejo combinando información de múltiples notas."""
        thread_id = str(uuid.uuid4())
        payload = {
            "message": "Compará mis notas sobre KEDA con las de la auditoría de Kafka y haceme una tabla de riesgos, luego guarda ese analisis en la base de conocimineto.",
            "thread_id": thread_id,
            "user_info": {"user_id": self.user_id, "is_stress_test": True},
            "prompt_version": os.getenv("PROMPT_VERSION", "rag_v4")
        }
        self._process_stream("Ultra Complex Task", payload)

    @task(2)
    def upload_heavy_document(self):
        """Simula la subida de un documento pesado con timeout extendido."""
        heavy_content = generate_heavy_unique_text().encode('utf-8')
        doc_name = f"stress_doc_{uuid.uuid4().hex[:8]}.txt"
        
        files = {
            'file': (doc_name, heavy_content, 'text/plain')
        }
        data = {
            'user_id': self.user_id,
            'document_date': datetime.now().strftime("%Y-%m-%d")
        }
        # Sincronizamos con timeout y catch_response de locustfile.py
        with self.client.post("/api/ingest", files=files, data=data, catch_response=True, timeout=120) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Ingest Failed: {response.status_code} - {response.text}")

