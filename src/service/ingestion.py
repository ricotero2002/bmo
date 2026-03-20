import io
import re
import os
import logging
from datetime import datetime, timezone
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
        logging.info(f"Iniciando conversión con MarkItDown para {filename} ({ext})")
        result = self.md.convert_stream(stream, file_extension=ext)
        logging.info(f"Conversión completada. Caracteres extraídos: {len(result.text_content)}")
        
        return self._clean_text(result.text_content)

    def _clean_text(self, text: str) -> str:
        """Limpieza básica respetando el formato Markdown (tablas, indentaciones)."""
        if not text:
            return ""
        return text.strip()

    def create_document(self, text: str, filename: str, 
                    file_hash: str = None,        # ← NUEVO
                    user_id: str = None,
                    page_number: int = None,       # ← NUEVO
                    chunk_index: int = None) -> Document:
        """Envuelve el texto en el formato que espera LangChain."""
        metadata = {
            "source": filename,
            "file_hash": file_hash,
            "created_at": datetime.now(timezone.utc).timestamp(),  # Unix timestamp (float) requerido por ChromaDB $gte
            "page_number": page_number,
            "chunk_index": chunk_index,
        }
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
            cleanup="incremental",
            source_id_key="source",  # Agrupa todos los chunks del mismo archivo bajo el mismo 'source'
        )