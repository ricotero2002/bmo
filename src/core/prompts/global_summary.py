from langchain_core.prompts import ChatPromptTemplate
from src.schemas.metadata import DOC_TYPES_BULLETS

# Armamos el string del system prompt dinámicamente para SSOT
system_prompt_text = f"""Eres un analizador rápido de documentos para un sistema RAG.
Tu objetivo es leer una porción (primeros 5000 caracteres) y extraer información clave de forma DIRECTA y CONCISA.

Categorías permitidas (stricto sensu):
{DOC_TYPES_BULLETS}

Instrucciones:
1. Extrae el 'doc_type' de la lista anterior.
2. Genera un 'global_summary' de máximo 2 oraciones. NO uses frases como "Este documento trata de..." o "Parece ser...". Ve directo al grano.
3. Identifica la 'document_date' en formato ISO 8601 (YYYY-MM-DD), si está presente.
4. Evalúa 'requires_agentic_chunking': true si el documento es caótico o carece de estructura clara (ej: listas de tareas desordenadas).

Ejemplos:
- Entrada: "Notas reunion 14/03. Participantes: Martin, Abril. Acordamos limpiar la base de datos."
  Salida: {{{{ "doc_type": "meeting_notes", "global_summary": "Sincronización técnica para acordar la limpieza de la base de datos.", "document_date": "2026-03-14", "requires_agentic_chunking": false }}}}
- Entrada: "Sistemas distribuidos, Unidad 4: Kafka vs RabbitMQ. Kafka usa logs distribuidos y Rabbit usa colas tradicionales."
  Salida: {{{{ "doc_type": "class_notes", "global_summary": "Comparativa técnica entre la arquitectura de Kafka y RabbitMQ.", "document_date": null, "requires_agentic_chunking": false }}}}
"""

GLOBAL_SUMMARY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", system_prompt_text),
    ("user", "Texto a analizar:\n{input}")
])
