from fastapi import Request
from src.providers.vector_store.factory import VectorStoreFactory
from src.service.ingestion import ExtractionService
from src.providers.database.status_provider import StatusProvider
from src.providers.storage.factory import StorageFactory

def get_vector_db(request: Request):
    return request.app.state.vector_store

def get_embeddings():
    return VectorStoreFactory.get_embeddings()

def get_record_manager(request: Request):
    return request.app.state.record_manager

def get_llm_factory(request: Request):
    return request.app.state.llm_factory

def get_extraction_service():
    return ExtractionService()

def get_chunking_service():
    from src.service.chunking import ChunkingService
    return ChunkingService()

def get_checkpointer(request: Request):
    return request.app.state.checkpointer

def get_agent_service(request: Request):
    return request.app.state.agent_service

def get_status_provider(request: Request):
    return request.app.state.status_provider

def get_storage_provider(request: Request):
    return request.app.state.storage_provider

def get_orchestrator(request: Request):
    from src.service.orchestrator import IngestionOrchestrator
    return IngestionOrchestrator(
        status_provider=request.app.state.status_provider,
        storage_provider=request.app.state.storage_provider
    )