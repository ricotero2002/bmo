
B. Testear el Chunking y Embeddings (Integration Test del RAG)
Para probar si tu Vector Database y tu estrategia de Chunking son buenas, no puedes mockear la semántica. Necesitas probar la matemática real de los vectores.

Para que esto funcione en un CI/CD sin levantar contenedores pesados, se hace lo siguiente:

Usar una Vector DB en memoria: En lugar de Redis Stack o PostgreSQL con pgvector, en tu entorno de test inicializas ChromaDB en modo efímero o FAISS. Viven en la RAM y mueren cuando termina el test.

El Golden Dataset de Retrieval: Creas un pequeño set de documentos (ej. 5 PDFs de prueba) y los ingestas en esa base de datos en memoria al inicio del test.

Métricas de DeepEval para RAG: Aquí no evalúas al agente, evalúas directamente tu función de búsqueda (tu retriever).

Usarías estas métricas específicas de DeepEval:

Contextual Precision (Precisión): ¿Los chunks más relevantes aparecieron primeros en la lista de resultados?

Contextual Recall (Exhaustividad): ¿El retriever trajo toda la información necesaria para responder, o dejó un pedazo clave afuera?

El test se vería así:

Python
from deepeval.metrics import ContextualPrecisionMetric, ContextualRecallMetric
from deepeval.test_case import LLMTestCase

## Este test no usa al agente, prueba directo tu motor de búsqueda
async def test_rag_retrieval_quality():
    # 1. Tu retriever real (conectado a Chroma/FAISS en memoria)
    retriever = get_test_vector_db() 
    
    pregunta = "¿Cuántos días de vacaciones tengo?"
    nodo_esperado = "El empleado tiene 15 días hábiles..." # Lo que DEBERÍA encontrar
    
    # 2. Ejecutar la búsqueda real (pasa por tu modelo de Embeddings real)
    documentos_recuperados = retriever.similarity_search(pregunta, k=3)
    contexto_real = [doc.page_content for doc in documentos_recuperados]

    # 3. Evaluar con DeepEval
    test_case = LLMTestCase(
        input=pregunta,
        actual_output="No importa para esta métrica",
        expected_output=nodo_esperado,
        retrieval_context=contexto_real
    )
    
    precision = ContextualPrecisionMetric(threshold=0.8)
    recall = ContextualRecallMetric(threshold=0.8)
    
    assert_test(test_case, [precision, recall])