import pytest
import os
from langchain_core.documents import Document
from src.service.chunking import ChunkingRouter, AgenticChunker


class DummyAgentResponse:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def get(self, key, default=None):
        return self.kwargs.get(key, default)


class DummyAgent:
    """Mock agent to avoid external API calls during chunking tests."""
    def __init__(self, response_format=None):
        self.response_format = response_format

    def invoke(self, inputs):
        if self.response_format:
            # Depending on the expected format
            name = self.response_format.__name__
            if name == "Sentences":
                # Mock returning a list of sentences natively
                return DummyAgentResponse(
                    sentences=["Oración falsa de prueba 1.", "Oración falsa de prueba 2."]
                )
            elif name == "ChunkID":
                # Mock returning no chunk id to force new chunk
                return DummyAgentResponse(chunk_id=None)
        
        # Default mock: return an object that has a .content property
        return type("Msg", (object,), {"content": "Resumen falso"})


class DummyLLMFactory:
    def create(self, response_format=None):
        return DummyAgent(response_format=response_format)

@pytest.fixture
def llm_factory():
    return DummyLLMFactory()


@pytest.fixture
def chunking_router():
    return ChunkingRouter()


def test_chunking_router_routes_to_markdown_for_structured_txt(chunking_router, llm_factory):
    # Cargar archivo estructurado (simulado ".txt")
    fixture_path = os.path.join(os.path.dirname(__file__), "..", "fixtures", "sample_structured.txt")
    with open(fixture_path, "r", encoding="utf-8") as f:
        text = f.read()

    # Tiene que redirigir al MarkdownTextSplitter porque tiene '# '
    chunks = chunking_router.route_and_split(llm_factory, text, filename="sample_structured.txt")
    
    assert len(chunks) > 0
    assert isinstance(chunks[0], Document)
    # Por defecto MarkdownTextSplitter no mete metadatos 'chunk_type' pero veamos si al menos lo partió
    # Y validamos que no lo dividió con el AgenticChunker (que daría metadata 'chunk_type': 'agentic')
    assert "chunk_type" not in chunks[0].metadata


def test_chunking_router_routes_to_agentic_for_short_unstructured_txt(chunking_router, llm_factory):
    # Cargar archivo no estructurado y corto
    fixture_path = os.path.join(os.path.dirname(__file__), "..", "fixtures", "sample_short.txt")
    with open(fixture_path, "r", encoding="utf-8") as f:
        text = f.read()

    # Debería usar AgenticChunker
    chunks = chunking_router.route_and_split(llm_factory, text, filename="sample_short.txt")
    
    assert len(chunks) > 0
    assert isinstance(chunks[0], Document)
    # Validamos que tiene la Metadata asignada por el AgenticChunker
    assert chunks[0].metadata.get("chunk_type") == "agentic"
    assert "chunk_title" in chunks[0].metadata
    assert "chunk_summary" in chunks[0].metadata
