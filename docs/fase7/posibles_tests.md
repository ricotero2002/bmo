Phase 7: Real Golden Dataset Validation (LLM as a Judge)
Este plan detalla la creación de un entorno de pruebas real y automatizado para validar el fin-a-fin de la Fase 7, desde la ingesta con metadatos inteligentes hasta la respuesta final del RAG.

User Review Required
CAUTION

Costos de API: Este test realizará llamadas reales a Gemini Flash para cada documento y cada evaluación del "Juez".
Ingesta Real: Se escribirán datos en el Vector Store (ChromaDB/Pinecone). Usaremos un user_id único (test_user_golden) para que el cleanup sea seguro.
Configuración: Asegúrate de que las variables de entorno (GOOGLE_API_KEY, etc.) estén correctamente configuradas en el entorno donde se corra el test.
Proposed Changes
1. Dataset de Prueba Estructurado
[NEW] 
test_golden_dataset_e2e.py
Definir la clase GoldenCase para estructurar: Contenido, Pregunta, Respuesta Esperada y Metadatos Esperados.
Implementar los 3 casos provistos: meeting_notes, class_notes, brainstorming.
2. Implementación del "LLM as a Judge"
Crear funciones auxiliares en el test para:
judge_metadata: Evaluar si el doc_type y global_summary extraídos son semánticamente correctos.
judge_rag_answer: Comparar la respuesta del agente contra la "Respuesta Golden" basándose en completitud y veracidad.
verify_retrieval_logic: Inspeccionar los pasos del agente para confirmar que el filtro doc_type fue utilizado correctamente.
3. Flujo de Ejecución del Test
Inicialización: Limpiar cualquier dato previo del test_user_golden.
Fase de Ingesta:
Procesar documentos con ChunkingService real.
Validar metadatos con el Juez.
Indexar en el Vector Store.
Fase de Preguntas:
Ejecutar el Agente langgraph con las preguntas Golden.
Recuperar trazas de las herramientas para verificar el filtrado.
Validar la respuesta final con el Juez.
Cleanup: Eliminar documentos indexados.
Verification Plan
Automated Tests
Ejecutar el test completo: pytest src/tests/integration/test_golden_dataset_e2e.py
Generar un reporte de "Puntaje Golden" basado en las evaluaciones del Juez.
Open Questions
Ambiente de Base de Datos: ¿Prefieres que usemos una colección de test separada o simplemente filtramos por user_id en la colección actual (recomendado para simplificar)?
Modelo del Juez: ¿Usamos Gemini 1.5 Flash para el juez (más económico) o Gemini 1.5 Pro (más preciso para evaluar)?





pytest src/evals/test_rag_agentic.py::test_rag_performance -v -s

$env:SKIP_INGEST="1"; pytest src/evals/test_rag_agentic.py::test_rag_performance -v -s