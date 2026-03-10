# Problem
El Problema: A lo largo del tiempo, generamos y guardamos información valiosa que queda fragmentada y aislada en múltiples "silos" (correos electrónicos, Google Drive, repositorios de GitHub, notas locales). El problema no es solo almacenar, sino la incapacidad de los métodos tradicionales de búsqueda (basados en palabras clave) para recuperar esa información, encontrar relaciones ocultas o permitirnos reflexionar sobre ella en lenguaje natural.
Impacto: Pérdida de conocimientos útiles, incapacidad para descubrir patrones de comportamiento (ej. "¿Cuáles son los géneros de libros que más leo últimamente?") y tiempo perdido buscando datos específicos en distintas plataformas.
La Solución: Un Asistente de Conocimiento Personal basado en Inteligencia Artificial. Este sistema utilizará una arquitectura GraphRAG que no solo recupere texto (mediante vectores), sino que construya un Grafo de Conocimiento interconectado para entender las relaciones entre distintas piezas de información. Esto permitirá al usuario interactuar, analizar y generar planes de acción sobre sus propios datos.


# Version Python
Analizando cuidadosamente la imagen que compartiste en tu mensaje anterior, tu proyecto se divide en 4 grandes desafíos que tu entorno debe soportar:
Building vector databases (Construcción de bases de datos vectoriales).
Implementing retrieval-augmented generation (RAG) (Implementación de RAG).
Handling privacy and security for personal data (Manejo de privacidad y seguridad de datos personales).
Creating a seamless chat interface (Creación de una interfaz de chat fluida).
Para garantizar la máxima compatibilidad con todos estos pilares en este 2026, te recomiendo firmemente utilizar Python 3.12 para tu entorno virtual.
Aquí te explico por qué es la versión óptima para tu stack técnico:
Compatibilidad con la Capa Gratuita de AWS Lambda: Si planeas desplegar tu orquestador o la extracción de datos en AWS Lambda para no gastar dinero, debes saber que AWS comenzó a retirar el soporte para Python 3.9 (ya no se pueden crear funciones nuevas con esa versión desde el 15 de enero de 2026). AWS Lambda actualmente soporta Python 3.11, 3.12, 3.13 y 3.14 sobre su sistema operativo Amazon Linux 2023. Python 3.12 es actualmente el "punto de equilibrio" ideal: es extremadamente estable, ampliamente adoptado y libre de los problemas de compilación que a veces tienen las versiones recién salidas (como la 3.14) al usar librerías de C++ por debajo.
Soporte para RAG y Bases Vectoriales (Puntos 1 y 2 de tu imagen): Herramientas clave de evaluación como DeepEval requieren versiones de Python >= 3.9. Además, los conectores de LangGraph, Neo4j y los clientes de bases vectoriales (como ChromaDB o AWS OpenSearch) están profundamente optimizados para el manejo de tipos (typing) avanzado y características que maduraron en Python 3.12, evitando conflictos de dependencias.
Manejo de Privacidad y Seguridad (Punto 3 de tu imagen): Si vas a proteger los datos personales de tus documentos para que el LLM no filtre información sensible, probablemente uses herramientas de enmascaramiento o librerías como NeMo Guardrails. Python 3.12 ofrece mejoras de rendimiento y gestión de memoria que son críticas para ejecutar estas validaciones de seguridad en milisegundos antes de que el prompt llegue a la API de Gemini u OpenAI.
Interfaz de Chat Fluida (Punto 4 de tu imagen): Para lograr una experiencia fluida (streaming de texto), tu backend usará FastAPI y procesos asíncronos. El módulo asyncio recibió mejoras masivas de rendimiento estructural en Python 3.11 y 3.12, lo que te permitirá manejar múltiples websockets o conexiones concurrentes hacia tu UI (en React o Streamlit) con una latencia mínima.

# Vector_store
patron de factory para poder cambiar facilmente entre la version de pruebas/develpment local y la version en produccion usando la nube.


# Guardado de archivos
## Arreglar problemas para gaurdar archivos
Arreglar como se ven los /n
## Pasar la logica de extraccion de pdfs fuera del endpointS
Pasar la logica a un servis llamado ingestion.py para la extraccion de los pdfs, limpieza y cracion de los documentos.
## Acomodar los metadatos, guardado de archivos y su organizacion


llevar un registro de los documentos/archivos guardados y poder ver como se guardaron, ver si necesito o no un bd aparte.

1. La opción "Pro": LangChain Indexing API
LangChain ofrece una herramienta llamada RecordManager diseñada específicamente para sincronizar documentos con bases vectoriales.

Cómo funciona: Calcula un hash único para cada fragmento de texto. Guarda estos hashes en una tabla SQL (SQLite o PostgreSQL).

Manejo de versiones: Si subes el mismo archivo con cambios menores, el sistema detecta qué partes son nuevas, cuáles cambiaron y borra automáticamente los vectores viejos.

Código conceptual:

Python

from langchain.indexes import SQLRecordManager, index

record_manager = SQLRecordManager(
    namespace=f"chroma/{collection_name}", 
    db_url="sqlite:///record_manager_cache.sql" # Local
    # db_url="postgresql://..." # Producción (RDS)
)
index(docs, record_manager, vectorstore, cleanup="incremental", source_id_key="source")

What SQLRecordManager Actually Does
Think of SQLRecordManager as the "memory" of your RAG system. It tracks which documents have been indexed and uses timestamps to determine what's changed. But it's much more sophisticated than a simple file tracker.

Here's what happens under the hood:

Record Tracking: Every time a document chunk gets indexed, the RecordManager creates a record with:

The document's unique identifier
A timestamp of when it was processed
A hash of the content
Metadata about the source
Smart Updates: When you run incremental indexing, it automatically cleans up outdated document versions while minimizing the time both old and new versions exist in the system. This means:

No duplicate embeddings cluttering your vector store
Automatic removal of outdated content
Efficient processing that only handles changed files
Cleanup Modes: The system offers different cleanup strategies:

Incremental: Continuously cleans up documents during indexing, removing outdated versions associated with source IDs that were processed
Full: Complete cleanup after indexing, ensuring only the latest versions remain
None: No automatic cleanup (useful for append-only scenarios)




# diferentes chunkings

Plantear el sistema para chequear diferentes formas de chunking, ver cual es mejor y si usar o no distinto segun el tipo. Y poder de forma deterministica su comparacion y como es mejor segun como se quiera luego hacer tambien la extraccion.

Adaptive Chunking
The system chooses chunking methods based on file state - semantic for new/changed files, text splitting for quick updates.


docker compose exec api pytest src/tests/unit/test_chunking.py


# Debugging Visual (Dashboard de Administración)
Para ver "qué hay dentro" sin entrar a la consola de la base de datos:

Streamlit (Panel de Debug): Puedes crear una página interna de administración con Streamlit para visualizar tus colecciones de Chroma en forma de tabla o DataFrame.
(con que me devuelva los diferentes archivos y sus chunks internos me alcanza igual)

Chroma Explorer / Chroma Flow Studio: Son herramientas externas que puedes conectar a tu contenedor de Docker para inspeccionar las colecciones, metadatos y embeddings de forma visual.

# hacer el agente real
poder preguntar realmente a un agente cosas en base a mis datos y que quizas tenga alguna otra tool
La idea es hacer el agente con langgraph. Ver como es la mejor forma de pasarle al agente la posibllidad de acceder a los datos. Algo como un Adaptive Rag quizas o similar.

Acomodar el agent, hacer que pueda devolver en forma de stream /ask, refactorizar agent de core para que en realidad sea llm_factory.

Ahora falta agregarle prompts para que utilize su retriver siempre que pueda.


Hacer guardrild viendo si los documentos tienen relevancia y que solo devuelva info chequeada.


Agregar resumen de conversaciones si muy largas.

agregar Transient Errors and Systemic Resilience.



# Hacer test de integracion:


B. Tests de Integración (Con servidores reales)
Aquí pruebas que la conexión con ChromaDB en Docker funciona realmente.

Opción Recomendada (Testcontainers): Es la mejor práctica de 2025. Levanta un contenedor temporal de Chroma solo para el test y lo borra al terminar.

Ejemplo con testcontainers en tests/conftest.py:

Python

import pytest
from testcontainers.chroma import ChromaContainer

@pytest.fixture(scope="session")
def chroma_server():
    with ChromaContainer() as chroma:
        # Obtenemos la URL del contenedor temporal
        server_url = chroma.get_connection_url()
        yield server_url

@pytest.fixture
def test_client(chroma_server):
    # Forzamos a la app a usar el servidor temporal de test
    app.state.vector_store_url = chroma_server 
    with TestClient(app) as client:
        yield client
Arreglar que al no usar el embeddings en la api no funciona la dependencia en el test
probar todo (para eso voy a tener que crear algun archivo que pruebe todo, estaria bueno poder probarlo en local y luego que se use en una git actions para produccion)
