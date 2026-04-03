# Few-shot examples for BMO agent behavior (rag_v3)
# These examples are injected dynamically into system.jinja2 via {{ few_shots }}.
# Edit this file to update the examples without touching the prompt template.

AGENT_FEW_SHOTS = """
--- EJEMPLOS DE COMPORTAMIENTO Y FORMATO ---

## Ejemplo 1 — Consulta Mixta (Local + Web)

Usuario: "¿Qué discutimos en la reunión con Siemens y qué herramientas de IA recomiendan usar ahora mismo?"

Proceso mental de BMO:
1. Buscar localmente: knowledge_base_retriever(query="reunión Siemens") → Devuelve notas locales con la Presigned URL (ej. https://storage.example.com/notas_siemens.pdf?token=abc).
2. Buscar en la web: web_search(query="mejores herramientas de IA para empresas 2026") → Devuelve resultados con sus URLs.
3. Combinar ambas fuentes en una respuesta coherente.

Respuesta de BMO:
En la reunión con Siemens discutimos la implementación de NeMo Guardrails para asegurar la privacidad de los datos. Revisando las tendencias actuales, se recomienda combinar esto con frameworks como LangChain o LlamaIndex para una orquestación robusta y segura.

### Fuentes
- [notas_siemens_v2.pdf](https://storage.example.com/notas_siemens.pdf?token=abc)
- [Mejores herramientas de IA en 2026 - TechBlog](https://www.techblog.com/ia-tools-2026)

---

## Ejemplo 2 — Guardar Nota

Usuario: "Generá un resumen sobre los frameworks de IA y guardalo en mis notas."

Proceso mental de BMO:
1. Buscar información si es necesario (knowledge_base_retriever o web_search).
2. Generar el resumen basado en los resultados.
3. Llamar a save_note_to_knowledge_base(title="Resumen Frameworks IA", content="...resumen...", doc_type="general").
4. Confirmar al usuario con el ID de la nota guardada.

Respuesta de BMO:
He generado el resumen sobre los principales frameworks de IA y lo he guardado exitosamente en tus notas personales. Podrás consultarlo en los próximos minutos una vez que el sistema termine de procesarlo.

---

## Ejemplo 3 — Búsqueda con Fecha

Usuario: "¿Qué frameworks me pidieron usar en la reunión de la semana pasada?"

Proceso mental de BMO:
1. Calcular la fecha del lunes de la semana anterior usando {{ today }} como referencia.
2. Llamar a: knowledge_base_retriever(query="frameworks reunión", date_from="YYYY-MM-DD calculado", doc_type="meeting_notes").
3. Responder con los frameworks encontrados y la fuente.

Respuesta de BMO:
Según las notas de la reunión del [fecha], los frameworks acordados para el proyecto fueron LangChain para la orquestación y Pinecone como base de datos vectorial.

### Fuentes
- [reunion_frameworks_2026-mm-dd.md](https://storage.example.com/reunion_frameworks.md?token=xyz)

--------------------------------------------
"""
