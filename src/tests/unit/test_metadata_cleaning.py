import pytest
from src.service.ingestion import ExtractionService
from langchain_core.documents import Document

def test_create_document_excludes_none_values():
    """
    Verifica que ExtractionService.create_document no incluya campos con valor None
    en el diccionario de metadata, lo cual es vital para la compatibilidad con Pinecone.
    """
    service = ExtractionService()
    
    # Caso 1: Con múltiples valores None, incluyendo file_hash
    doc = service.create_document(
        text="test content",
        filename="test.pdf",
        file_hash=None,      # <-- Ahora forzamos que sea None
        user_id="user_123",
        page_number=None,
        chunk_index=None
    )
    
    # Assertions
    assert doc.metadata["source"] == "test.pdf"
    assert doc.metadata["user_id"] == "user_123"
    assert "file_hash" not in doc.metadata  # <-- Verificamos que no exista
    assert "page_number" not in doc.metadata
    assert "chunk_index" not in doc.metadata
    assert isinstance(doc.metadata["created_at"], float)

def test_chunk_index_persistence_in_service():
    """
    Verifica que si pasamos parámetros válidos, sí se mantengan.
    """
    service = ExtractionService()
    doc = service.create_document(
        text="test",
        filename="test.pdf",
        chunk_index=5,
        file_hash="hash_real"
    )
    assert doc.metadata["chunk_index"] == 5
    assert doc.metadata["file_hash"] == "hash_real"
