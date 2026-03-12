import io
import re
import os
from markitdown import MarkItDown
from langchain_core.documents import Document
from langchain_classic.indexes import index
from typing import Optional

class ExtractionService:
    def __init__(self):
        self.md = MarkItDown()

    def extract_text_from_bytes(self, content: bytes, filename: str) -> str:
        """Extrae el texto de los bytes usando MarkItDown en memoria."""
        # Obtenemos la extensión del archivo a partir del nombre en minúscula
        _, ext = os.path.splitext(filename)
        ext = ext.lower()
        
        # Creamos el stream en memoria
        stream = io.BytesIO(content)
        
        # MarkItDown soporta la mayoría de formatos si le damos el stream y la extensión
        result = self.md.convert_stream(stream, file_extension=ext)
        
        return self._clean_text(result.text_content)

    def _clean_text(self, text: str) -> str:
        """Limpieza básica respetando el formato Markdown (tablas, indentaciones)."""
        if not text:
            return ""
        return text.strip()

    def create_document(self, text: str, filename: str, user_id: Optional[str] = None) -> Document:
        """Envuelve el texto en el formato que espera LangChain."""
        metadata = {"source": filename}
        if user_id:
            metadata["user_id"] = user_id
        return Document(
            page_content=text, 
            metadata=metadata
        )
    def index_documents(self, chunks, record_manager, vector_store):
        return index(
            docs_source=chunks,
            record_manager=record_manager,
            vector_store=vector_store,
            cleanup="incremental", # Can also be "full" or None
            source_id_key="source" # Or whatever key identifies unique documents
        )