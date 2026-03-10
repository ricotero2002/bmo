# 1. Ingesta Multiformato: De PyPDF2 a MarkItDown
Para soportar más que solo PDFs (Word, Excel, PPT, imágenes), la mejor práctica actual es utilizar la librería MarkItDown de Microsoft o Unstructured.io. Estas herramientas normalizan cualquier archivo a Markdown, lo que preserva la jerarquía (títulos, tablas, listas) que el RAG necesita.

Evolución del PDFService a UniversalExtractionService:

Python

from markitdown import MarkItDown

class ExtractionService:
    def __init__(self):
        self.md = MarkItDown()

    def to_markdown(self, file_path: str) -> str:
        # Detecta automáticamente si es PDF, DOCX, XLSX, etc.
        result = self.md.convert(file_path)
        return result.text_content
Justificación: Al convertir todo a Markdown, puedes usar splitters específicos que entienden encabezados (##), lo cual es mucho más preciso que contar caracteres.


docker compose exec api pytest src/tests/unit/test_pdf_service.py
docker compose exec api pytest src/tests/unit/test_api.py src/tests/unit/test_pdf_service.py -v

# 2. El Router de Chunking Adaptativo
Criterio,Estrategia,Justificación
Notas cortas / Diarios,Agentic (Propositional),Re-escribe frases sin contexto para que sean autónomas.
Libros / Artículos largos,Semantic Chunking ( o recursive),Detecta cambios de tema mediante similitud de embeddings.
Código (Python/JS),Language-Specific,Divide por funciones y clases para no romper la lógica.
Manuales / Reportes,Markdown Recursive,Respeta la jerarquía de títulos y sub-títulos.

# 3. Implementación de los Componentes
A. Semantic Chunking (Local/Prod)
Utiliza el SemanticChunker de LangChain. En local puedes usar modelos de HuggingFace y en producción AWS Bedrock para escalabilidad.

Breakpoint Threshold: Configura el percentil al 95%. Si la "distancia" entre el embedding de la frase A y la B es mayor al percentil 95 de todo el documento, se crea un corte.

B. Agentic/Propositional Chunking
Este es el "pata negra" del sistema. Usa un LLM para descomponer un párrafo en proposiciones atómicas (verdades independientes).

Ejemplo: "Él nació en Balcarce" → "Agustín Freire nació en la ciudad de Balcarce, Argentina".

Grouping: Una vez extraídas las proposiciones, el agente decide cuáles agrupar en un solo chunk basado en un resumen dinámico del tema.

Acomodar chunking, agent y middlewares. Aparte prompts deberia guardarse con versiones en archivos separados.


# 4. Evaluación Determinística con DeepEval
Para decidir "qué chunking es mejor", no puedes confiar en tu intuición. Debes crear un Benchmark de Recuperación.

Dataset de Oro (Goldens): Crea 20 preguntas basadas en un documento real donde ya sepas qué respuesta debería dar.

Métricas de Retriever: Ejecuta los diferentes tipos de chunking y mide:

Contextual Recall: ¿Está toda la información necesaria para responder en los chunks recuperados?

Contextual Precision: ¿Los chunks relevantes están en los primeros lugares?

Contextual Relevancy: ¿Cuánta "basura" o ruido hay en el contexto recuperado?

Ejemplo de Test en PyTest:
from deepeval.metrics import ContextualRelevancyMetric
from deepeval.test_case import LLMTestCase

def test_semantic_vs_recursive():
    metric = ContextualRelevancyMetric(threshold=0.7)
    test_case = LLMTestCase(
        input="¿Cuál es la experiencia de Agustín en microservicios?",
        actual_output="...", # Respuesta del RAG
        retrieval_context=["Chunk 1...", "Chunk 2..."] # Chunks que trajo el sistema
    )
    metric.measure(test_case)
    assert metric.is_successful()
