import pytest
from unittest.mock import MagicMock, patch
from langchain_core.documents import Document
from src.service.chunking import ChunkingService
from src.schemas.metadata import DocumentMetadataExtraction
from datetime import datetime, timezone

def test_chunking_service_injects_global_context_and_date():
    # 1. Setup Mock LLM Factory
    mock_llm_factory = MagicMock()
    mock_fast_agent = MagicMock()
    
    # Simular respuesta del GlobalSummarizer
    mock_context = DocumentMetadataExtraction(
        doc_type="financial_legal",
        global_summary="Una factura de servicios de internet de marzo.",
        document_date="2026-03-15",
        requires_agentic_chunking=False
    )
    mock_fast_agent.invoke.return_value = mock_context
    
    # Configurar el factory para devolver el mock agent cuando se pida DocumentMetadataExtraction
    mock_llm_factory.create_lite.return_value = mock_fast_agent
    
    service = ChunkingService()
    
    # 2. Documento de prueba
    doc = Document(
        page_content="Contenido de la factura de internet de marzo 2026. Monto total: $1500.",
        metadata={"source": "factura_marzo.pdf"}
    )
    
    # 3. Procesar
    chunks = service.process(doc, mock_llm_factory)
    
    # 4. Verificaciones
    assert len(chunks) > 0
    first_chunk = chunks[0]
    
    # Verificar inyección de texto
    assert "[Contexto Global de financial_legal: Una factura de servicios de internet de marzo.]" in first_chunk.page_content
    
    # Verificar metadata
    assert first_chunk.metadata["doc_type"] == "financial_legal"
    assert first_chunk.metadata["document_date_str"] == "2026-03-15"
    
    # Verificar conversión de fecha (timestamp de 2026-03-15)
    expected_ts = datetime(2026, 3, 15, tzinfo=timezone.utc).timestamp()
    assert first_chunk.metadata["created_at"] == expected_ts

def test_chunking_service_respects_manual_date():
    mock_llm_factory = MagicMock()
    mock_fast_agent = MagicMock()
    
    # LLM detecta una fecha (2025), pero el usuario mandó otra (2026)
    mock_context = DocumentMetadataExtraction(
        doc_type="general",
        global_summary="Resumen",
        document_date="2025-01-01",
        requires_agentic_chunking=False
    )
    mock_fast_agent.invoke.return_value = mock_context
    mock_llm_factory.create_lite.return_value = mock_fast_agent
    
    service = ChunkingService()
    
    # El usuario pasó fecha manual (ya viene en metadata gracias a tasks.py/ingestion.py)
    manual_date_ts = datetime(2026, 12, 31, tzinfo=timezone.utc).timestamp()
    doc = Document(
        page_content="Texto de prueba",
        metadata={
            "source": "test.txt",
            "created_at": manual_date_ts,
            "custom_date": True,
            "document_date_str": "2026-12-31"
        }
    )
    
    chunks = service.process(doc, mock_llm_factory)
    
    # Debería prevalecer la fecha manual (2026) sobre la detectada (2025)
    assert chunks[0].metadata["created_at"] == manual_date_ts
    assert chunks[0].metadata["document_date_str"] == "2026-12-31"

def test_agentic_chunker_removes_unnecessary_metadata():
    # Verificar que chunk_title y chunk_summary NO están presentes en los chunks finales
    mock_llm_factory = MagicMock()
    mock_agent = MagicMock()

    # Agentes especializados devuelven resultados exitosos
    mock_sentences_agent = MagicMock()
    mock_sentences_agent.invoke.return_value = MagicMock(sentences=["Oración 1."])
    
    mock_chunk_id_agent = MagicMock()
    mock_chunk_id_agent.invoke.return_value = MagicMock(chunk_id=None)
    
    mock_plain_agent = MagicMock()
    mock_plain_agent.invoke.side_effect = [
        MagicMock(content="Resumen"), # _get_new_chunk_summary
        MagicMock(content="Titulo")   # _get_new_chunk_title
    ]

    # Mocking de agentes específicos dentro de AgenticChunker
    # .create_lite() se llama 3 veces en __init__
    mock_llm_factory.create_lite.side_effect = [
        mock_plain_agent,
        mock_sentences_agent,
        mock_chunk_id_agent
    ]

    from src.service.chunking import AgenticChunker
    agentic = AgenticChunker(mock_llm_factory)

    # El texto de entrada debe disparar el proceso (que mockeamos arriba)
    docs = agentic.chunk("Texto de prueba.")

    assert len(docs) == 1
    meta = docs[0].metadata
    assert "chunk_title" in meta
    assert "chunk_summary" in meta
    assert meta["chunk_type"] == "agentic"
