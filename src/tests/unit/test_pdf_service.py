import pytest
from unittest.mock import patch, MagicMock
from src.service.ingestion import ExtractionService

def test_extraction_cleaning_logic():
    service = ExtractionService()
    
    # Simulamos el texto sucio y verificamos que NO arruina tablas ni doble saltos de linea
    dirty_text = "   # Título \n\n | Col 1 | Col 2 |\n|---|---|\n| A | B |    "
    
    clean_text = service._clean_text(dirty_text)
    
    # Verificamos que se mantienen los espacios de la tabla, pero se limpian los extremos
    assert clean_text == "# Título \n\n | Col 1 | Col 2 |\n|---|---|\n| A | B |"

def test_document_creation():
    service = ExtractionService()
    doc = service.create_document("contenido de prueba", "test.md")
    
    assert doc.metadata["source"] == "test.md"
    assert doc.page_content == "contenido de prueba"

@patch('src.service.ingestion.MarkItDown')
def test_extract_text_multiple_formats(mock_markitdown):
    mock_md_instance = MagicMock()
    mock_result = MagicMock()
    mock_result.text_content = "# Contenido extraído"
    mock_md_instance.convert_stream.return_value = mock_result
    mock_markitdown.return_value = mock_md_instance
    
    service = ExtractionService()
    service.md = mock_md_instance
    
    # Prueba CSV
    res = service.extract_text_from_bytes(b"dummy,csv", "archivo.csv")
    assert res == "# Contenido extraído"
    args, kwargs = mock_md_instance.convert_stream.call_args
    assert kwargs.get("file_extension") == ".csv"
    
    # Prueba XLSX con mayúsculas
    service.extract_text_from_bytes(b"dummy bytes", "planilla.XLSX")
    args, kwargs = mock_md_instance.convert_stream.call_args
    assert kwargs.get("file_extension") == ".xlsx"

    # Prueba DOCX
    service.extract_text_from_bytes(b"dummy bytes", "reporte.docx")
    args, kwargs = mock_md_instance.convert_stream.call_args
    assert kwargs.get("file_extension") == ".docx"