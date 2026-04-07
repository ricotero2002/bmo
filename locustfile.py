import time
import json
import uuid
import random
from locust import HttpUser, task, between, events

TEST_USER_ID = "locust_tester"

# Batería de preguntas sacadas de tu Golden Dataset
QUERIES = [
    "¿Cómo decidiste optimizar la lógica de ruteo del agente para bajar la latencia?",
    "Tengo una entrevista con Siemens pronto, ¿qué herramientas específicas iba a mencionar en la presentación para demostrar conocimientos en privacidad y AI Safety?",
    "¿Qué bases de datos voy a usar para resolver el problema de concurrencia en el tracking de las ingestas masivas?",
    "Haceme un resumen de los problemas que tuve con Kafka y Docker últimamente."
]

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
    for _ in range(100): 
        content += random.choice(paragraphs)
        if random.random() > 0.8: # Salto de línea aleatorio
            content += "\n"
            
    return content

class BMOUser(HttpUser):
    wait_time = between(2, 5)
    host = "http://localhost:8081"

    @task(10)
    def chat_streaming(self):
        thread_id = str(uuid.uuid4())
        query = random.choice(QUERIES)
        
        payload = {
            "message": query,
            "thread_id": thread_id,
            "prompt_version": "rag_v3",
            "user_info": {"user_id": TEST_USER_ID, "is_stress_test": True}
        }
        
        start_time = time.time()
        ttft_recorded = False

        # AGREGADO: timeout=120 para evitar que Locust corte la conexión bajo carga
        # y dispare los CancelledError en FastAPI/LangGraph.
        with self.client.post("/api/ask/stream", json=payload, stream=True, catch_response=True, timeout=120) as response:
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
                                    name="TTFT (Vectorial + LLM)",
                                    response_time=ttft * 1000,
                                    response_length=0,
                                )
                                ttft_recorded = True

                            if "[DONE]" in decoded_line:
                                break
                    
                    total_time = time.time() - start_time
                    events.request.fire(
                        request_type="SSE",
                        name="Total Chat Time",
                        response_time=total_time * 1000,
                        response_length=0,
                    )
                    response.success()
                except Exception as e:
                    response.failure(f"Stream interrupted: {str(e)}")
            else:
                response.failure(f"Error {response.status_code}")

    @task(1)
    def upload_heavy_document(self):
        # Generar contenido 100% único
        heavy_content = generate_heavy_unique_text().encode('utf-8')
        doc_name = f"stress_doc_{uuid.uuid4().hex[:8]}.txt"
        
        files = {
            'file': (doc_name, heavy_content, 'text/plain')
        }
        data = {
            'user_id': TEST_USER_ID,
            'document_date': '2026-04-07'
        }
        
        # AGREGADO: timeout=120 porque la subida y encolamiento pueden enlentecerse
        with self.client.post("/api/ingest", files=files, data=data, catch_response=True, timeout=120) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Ingest Failed: {response.text}")
