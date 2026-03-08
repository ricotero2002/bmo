from fastapi import Request
from src.providers.vector_store.factory import VectorStoreFactory
from src.service.ingestion import ExtractionService
def get_vector_db(request: Request):
    return request.app.state.vector_store

# Dependencia para el servicio de Embeddings (OpenAI, etc.)
def get_embeddings():
    # Aquí podrías usar una Factory según el entorno
    return VectorStoreFactory.get_embeddings()
#aca falta tambien el del llm.

def get_record_manager(request: Request):
    return request.app.state.record_manager

def get_agent_factory(request: Request):
    return request.app.state.agent_factory

def get_extraction_service():
    return ExtractionService()

def get_chunking_service():
    from src.service.chunking import ChunkingService
    return ChunkingService()