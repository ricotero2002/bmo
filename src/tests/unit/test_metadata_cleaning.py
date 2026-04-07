import pytest
from langchain_core.documents import Document

def test_metadata_cleaning_logic():
    """
    Verifica que la lógica de limpieza de metadatos (extraída de tasks.py)
    funciona correctamente y elimina valores None.
    """
    doc_id = "test-doc-id"
    filename = "test.txt"
    user_id = None # Simulamos que no hay user_id
    
    # Lógica copiada de tasks.py
    metadata_to_add = {
        "source": doc_id,
        "user_id": user_id,
        "filename": filename
    }
    clean_metadata = {k: v for k, v in metadata_to_add.items() if v is not None}
    
    # Aserciones
    assert "source" in clean_metadata
    assert "filename" in clean_metadata
    assert "user_id" not in clean_metadata
    assert clean_metadata["source"] == doc_id
    assert clean_metadata["filename"] == filename

def test_document_metadata_update():
    """
    Verifica que al actualizar un Document con metadatos limpios,
    no se introducen valores None.
    """
    doc = Document(page_content="test content", metadata={"old": "val"})
    
    clean_metadata = {
        "source": "123",
        "filename": "file.pdf"
        # user_id omitido porque es None
    }
    
    doc.metadata.update(clean_metadata)
    
    assert doc.metadata["source"] == "123"
    assert doc.metadata["filename"] == "file.pdf"
    assert "user_id" not in doc.metadata
    assert None not in doc.metadata.values()
