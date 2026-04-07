import requests
import time

API_URL = "http://localhost:8081/api/ingest"
TEST_USER_ID = "locust_tester"

# Tus datos del Golden Dataset V2
GOLDEN_DATASET = [
    {
        "name": "Test_1_Brainstorming.md",
        "raw_text": "Borrador de ideas de la madrugada. Estuve pensando seriamente en la migración de BMO. OKE me tiene cansado con las caídas de los nodos por falta de memoria, capaz me conviene armar un clúster de EKS en AWS aprovechando unos créditos que me dieron, o levantar EC2 directamente con K3s. El tema de los secretos lo quiero manejar sí o sí con Infisical, basta de andar pasando los .env hardcodeados o por chat. Por otro lado, estuve revisando los logs y la lógica de ruteo del agente está muy lenta. En vez de usar un solo LLM gigante para todo, voy a implementar una lógica de ruteo donde un modelo chiquito y rápido (tipo Haiku) solo clasifique la complejidad de la query, y en base a eso elija a qué agente o modelo pesado llamar. Ahorro latencia y plata. Che, me crucé con un artículo de GraphRAG y me voló la cabeza, pero creo que para las búsquedas de BMO, con sacar las relaciones directamente de la base de datos sin forzar a que sea específico con los schemas de Pydantic ya me alcanza, la otra vez falló todo por intentar tiparlo tan fuerte. Acordarme de decirle a Abril si quiere ir a merendar al centro mañana por nuestro aniversario. Ah, y sobre la facultad: para la presentación final de OOPingo tengo que armar bien el diagrama de la base de datos de Spring Boot, sobre todo la tabla donde guardo las mecánicas de gamificación que quedó medio confusa de explicar."
    },
    {
        "name": "Test_2_Meeting_Notes.md",
        "raw_text": "Llamada por Discord para preparar las entrevistas. La semana que viene tengo las entrevistas técnicas con Amperity y Siemens para el puesto de AI Engineer, y también mandé el CV a NEC. Les mostré a los chicos el speech que armé. Me recomendaron hacer muchísimo foco en AI Safety, privacidad de datos y ética, porque a las empresas grandes les importa un montón que no filtres datos de usuarios. Voy a sumar un slide a la presentación explicando cómo podemos implementar NeMo Guardrails y el enmascaramiento de PII en los pipelines de ingesta. En el medio de la charla quise levantar el entorno y se me crasheó el Docker Compose local; parece que el contenedor de RabbitMQ se quedó sin espacio en el volumen de Docker y arrastró a todos los workers de Celery a la muerte. Tengo que purgar los volúmenes con un `docker system prune` o subirle el límite al disco virtual hoy a la noche sin falta. Nada que ver, pero le tengo que transferir la mitad de las expensas al dueño del depto antes del viernes, siempre me olvido de eso."
    },
    {
        "name": "Test_3_PostMortem.md",
        "raw_text": "Post-mortem del problema de la Fase 3. Ayer intenté hacer la prueba de ingesta masiva de documentos y falló todo el pipeline. Los logs tiraban que MinIO estaba rechazando las conexiones que venían del broker. Empecé a revisar y el problema era que el consumidor asíncrono no estaba haciendo bien el commit de los offsets de los mensajes y se terminó generando un cuello de botella enorme en la persistencia. Lo solucioné temporalmente subiéndole el timeout al worker. Mientras debuggeaba esto, estaba escuchando de fondo una clase grabada sobre arquitecturas distribuidas. El profesor explicaba que usar un sistema como Apache Kafka está buenísimo para sistemas reactivos por su arquitectura de append-only log, pero que si no configurás bien la 'retention policy', te comés el disco entero del servidor en un par de días. Literalmente lo que me estuvo pasando a mí en el clúster. \nTareas que me quedan para este fin de semana:\n- Ajustar la política de retención de los topics a 24 horas.\n- Terminar de redactar el informe final de OOPingo.\n- Comprar las entradas para el cine para ir con mi novia.\n- Migrar el tracking de estado de las ingestas de SQLite a Postgres para que se banque mejor la concurrencia de los workers."
    }
]

def seed_database():
    print("🌱 Iniciando siembra de datos (Golden Dataset)...")
    for doc in GOLDEN_DATASET:
        files = {'file': (doc["name"], doc["raw_text"].encode('utf-8'), 'text/markdown')}
        data = {'user_id': TEST_USER_ID, 'document_date': '2026-04-07'}
        
        try:
            resp = requests.post(API_URL, files=files, data=data)
            if resp.ok:
                print(f"✅ Ingestado: {doc['name']}")
            else:
                print(f"❌ Error con {doc['name']}: {resp.text}")
        except Exception as e:
            print(f"💥 Error de conexión: {e}")
            
        time.sleep(1) # Pausa para no pisar las conexiones locales
    print("✨ Base de datos lista para pruebas de estrés.")

if __name__ == "__main__":
    seed_database()
