from typing import Literal, Optional, get_args
from pydantic import BaseModel, Field

# 1. Definimos la lista estricta de tipos de documentos.
DocType = Literal[
    "meeting_notes",
    "class_notes",
    "project_planning",
    "technical_doc",
    "research_paper",
    "tutorial_guide",
    "brainstorming",
    "troubleshooting",
    "financial_legal",
    "general"
]

# Obtenemos los valores dinámicamente para mantener una única fuente de verdad (SSOT)
AVAILABLE_DOC_TYPES = get_args(DocType)
DOC_TYPES_INLINE = ", ".join([f"'{t}'" for t in AVAILABLE_DOC_TYPES])
DOC_TYPES_BULLETS = "\n".join([f"{i+1}. {cat}" for i, cat in enumerate(AVAILABLE_DOC_TYPES)])

# 2. Esquema que el LLM debe completar en la fase de pre-chunking.
class DocumentMetadataExtraction(BaseModel):
    doc_type: DocType = Field(
        description=(
            f"Clasifica el documento estrictamente en una de las categorías: {DOC_TYPES_INLINE}. "
            "Usa 'meeting_notes' para reuniones, 'technical_doc' para arquitectura, "
            "'class_notes' para la facultad. Si no encaja, usa 'general'."
        )
    )
    
    global_summary: str = Field(
        description=(
            "Un resumen conciso y directo (máximo 2-3 líneas) sobre el contenido principal y el propósito del documento."
        )
    )
    
    document_date: Optional[str] = Field(
        default=None,
        description="La fecha principal del documento en formato ISO 8601 (YYYY-MM-DD), si se puede deducir."
    )

    requires_agentic_chunking: bool = Field(
        description="Indica si el documento es un caos sin estructura clara y requiere análisis semántico profundo para fragmentarse."
    )
