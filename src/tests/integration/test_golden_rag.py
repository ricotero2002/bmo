import pytest
from unittest.mock import MagicMock
from langchain_core.documents import Document
from src.service.chunking import ChunkingService
from src.schemas.metadata import DocumentMetadataExtraction

@pytest.fixture
def golden_documents():
    return [
        {
            "filename": "meeting_notes_daily_14_03.md",
            "content": """Notas de Reunión (meeting_notes_daily_14_03.md)
Fecha: 14 de Marzo de 2026
Participantes: Abril, Martín, Sofía.
Tema: Sincronización del proyecto de Asistente Personal.

Notas:
Abril comentó que la integración con LangGraph está funcionando bien, pero estamos teniendo problemas de memoria cuando el historial del RAG se hace muy largo. Propuso truncar los mensajes de las herramientas para no sobrepasar el límite de tokens de Oracle. Martín va a revisar el clúster de Kubernetes porque ayer tuvimos un pico de latencia en los workers de Celery al procesar PDFs grandes.

Action Items:
- Implementar un nodo de limpieza de memoria en el grafo (Abril).
- Escalar los pods de Celery en K8s a un mínimo de 3 réplicas (Martín).
- Revisar la configuración de los topics de Kafka para los eventos de ingesta.
""",
            "expected_metadata": {
                "doc_type": "meeting_notes",
                "document_date": "2026-03-14"
            }
        },
        {
            "filename": "clase_sistemas_distribuidos.txt",
            "content": """Materia: Sistemas Distribuidos Avanzados
Unidad 4: Procesamiento de flujos de datos (Stream Processing).

Kafka es una plataforma de streaming distribuida que nos permite publicar y suscribirnos a flujos de registros. A diferencia de las colas de mensajes tradicionales, Kafka retiene los mensajes durante un tiempo configurable (encluso si ya fueron leídos) y basa su rendimiento en el uso eficiente del page cache del sistema operativo y lecturas/escrituras secuenciales en disco.
Apache Spark, por otro lado, puede consumir datos de Kafka usando Spark Streaming. Spark procesa los datos en micro-lotes (micro-batches), lo que ofrece tolerancia a fallos mediante RDDs, aunque introduce una latencia ligeramente mayor comparado con sistemas de streaming puro como Flink.
""",
            "expected_metadata": {
                "doc_type": "class_notes",
                "document_date": None
            }
        },
        {
            "filename": "ideas_proyecto_tesis.md",
            "content": """Contexto: Lluvia de ideas para la arquitectura de la tesis.

El objetivo principal de la plataforma es tener módulos separados para alumnos y profesores.
Para el backend, estoy dudando entre usar FastAPI (con Python) o Spring Boot (con Java). FastAPI me permitiría integrar los modelos de Machine Learning mucho más fácil y armar prototipos rápidos. Sin embargo, Spring Boot tiene un ecosistema más robusto para patrones empresariales.

Pendientes:
- Armar un cuadro comparativo de rendimiento entre FastAPI y Spring Boot conectándose a una base de datos Neo4j.
- Investigar cómo usar Redis para cachear las respuestas frecuentes del módulo de alumnos.
""",
            "expected_metadata": {
                "doc_type": "brainstorming",
                "document_date": None
            }
        }
    ]

def test_golden_rag_pipeline(golden_documents):
    service = ChunkingService()
    mock_llm_factory = MagicMock()
    
    for doc_data in golden_documents:
        # Mocking el resumidor global para cada documento
        mock_agent = MagicMock()
        mock_context = DocumentMetadataExtraction(
            doc_type=doc_data["expected_metadata"]["doc_type"],
            global_summary="Resumen global de prueba",
            document_date=doc_data["expected_metadata"]["document_date"],
            requires_agentic_chunking=False
        )
        mock_agent.invoke.return_value = mock_context
        mock_llm_factory.create.return_value = mock_agent
        
        orig_doc = Document(
            page_content=doc_data["content"],
            metadata={"source": doc_data["filename"]}
        )
        
        chunks = service.process(orig_doc, mock_llm_factory)
        
        # Verificaciones básicas
        assert len(chunks) > 0
        assert chunks[0].metadata["doc_type"] == doc_data["expected_metadata"]["doc_type"]
        
        # Verificar que el contenido incluye el contexto global (Paso 1.1)
        assert f"[Contexto Global de {doc_data['expected_metadata']['doc_type']}:" in chunks[0].page_content
        
        # Verificar fecha si aplica (Paso 1.2)
        if doc_data["expected_metadata"]["document_date"]:
            assert chunks[0].metadata["document_date_str"] == doc_data["expected_metadata"]["document_date"]

def test_retriever_filter_mocked():
    from src.tools.metadata_filter import build_metadata_filter
    
    # Caso 1: Filtro explícito por doc_type (lo que pidió el usuario)
    filter_dict = build_metadata_filter(doc_type="meeting_notes")
    assert filter_dict == {"doc_type": {"$eq": "meeting_notes"}}
    
    # Caso 2: Filtro combinado (fecha + tipo)
    from datetime import datetime, timezone
    filter_dict = build_metadata_filter(date_from="2026-03-01", doc_type="financial_legal")
    
    assert "$and" in filter_dict
    conditions = filter_dict["$and"]
    assert any("doc_type" in c and c["doc_type"]["$eq"] == "financial_legal" for c in conditions)
    assert any("created_at" in c for c in conditions)
