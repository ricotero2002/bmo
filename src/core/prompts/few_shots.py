# Few-Shot Examples for Propositional Chunking
# Based on updated strict rules (No translation, Strict alignment, Contextual cohesion)

PROPOSITIONS_FEW_SHOTS = """
Example 1 (Spanish, Technical with Lists):
Input: "Bueno, arrancamos la llamada a las 18hs. Marcos me decía que Kafka es un overkill total para un proyecto personal. Tareas sueltas: Revisar por qué el MarkItDown falla con algunos PDFs. Implementar el borrado de memoria temporal en LangGraph."
Output: [
    "Arrancamos la llamada del proyecto personal BMO a las 18hs.",
    "Marcos sugirió que Kafka es un overkill total para el proyecto personal.",
    "Tareas pendientes del proyecto para hacer antes del domingo: 1) Revisar por qué el MarkItDown falla con algunos PDFs escaneados. 2) Implementar el borrado de memoria temporal en LangGraph."
]

Example 2 (Multilingual, Contextual):
Input: "Estuve viendo el schema de MongoDB del side project y es un desastre. Voy a migrar a PostgreSQL. Ah, me olvidé de comprar las cajas de cartón para la mudanza."
Output: [
    "El schema actual de MongoDB del side project es un desastre.",
    "Voy a migrar la base de datos del side project de MongoDB a PostgreSQL para manejar relaciones complejas.",
    "Debo comprar cajas de cartón para la mudanza al centro de Tandil."
]
"""

ROUTER_FEW_SHOTS = """
Example 1 (Strict Alignment):
Input Proposition: "Debo comprar cajas de cartón para la mudanza al centro de Tandil."
Current Chunks:
- Chunk (a1b2c): Logística de Mudanza
  Summary: Presupuesto de flete y trámites de Internet para la mudanza a Tandil.
- Chunk (d3e4f): Refactor Base de Datos
  Summary: Migración de MongoDB a PostgreSQL usando SQLAlchemy.
Output: a1b2c

Example 2 (No "Mega-Chunks"):
Input Proposition: "La latencia de los endpoints de lectura de la API está aumentando."
Current Chunks:
- Chunk (g5h6i): Refactor Base de Datos
  Summary: Migración de MongoDB a PostgreSQL para mejorar relaciones complejas.
Output: No chunks (Rationale: Different architectural component; Focus shifts from DB schema to API monitoring/latency)
"""
