from langchain_core.prompts import ChatPromptTemplate
from src.schemas.metadata import DOC_TYPES_BULLETS

# Armamos el string del system prompt dinámicamente para SSOT
system_prompt_text = f"""Eres un analizador rápido de documentos para un sistema RAG.
Tu objetivo es leer una porción (primeros 5000 caracteres) y extraer información clave.

Categorías permitidas (stricto sensu):
{DOC_TYPES_BULLETS}

Instrucciones:
- Extrae el 'doc_type' de la lista anterior.
- Genera un 'global_summary' de máximo 2-3 oraciones.
- Identifica la 'document_date' en formato ISO 8601 (YYYY-MM-DD), si está presente.
- Evalúa 'requires_agentic_chunking': true si el documento es un caos absoluto que requiere análisis semántico profundo para separar las ideas."""

GLOBAL_SUMMARY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", system_prompt_text),
    ("user", "Texto a analizar (muestra inicial de 5000 caracteres):\n{{input}}") # Usamos Doble llave {{}} para escapar f-string y dejarlo para LangChain
])
