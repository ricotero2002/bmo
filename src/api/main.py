from contextlib import asynccontextmanager
from fastapi import FastAPI
from src.providers.vector_store.factory import VectorStoreFactory
from src.providers.record_manager.factory import RecordManagerFactory
from src.core.llm import LLMFactory
from src.providers.checkpointer.factory import CheckpointerFactory
from src.api.endpoints import router as api_router
from src.api.debug import router as debug_router
from src.service.agent import AgentService
from langchain_core.tools.retriever import create_retriever_tool
from src.tools.registry import ToolRegistry
from src.providers.database.status_provider import StatusProvider
from src.providers.storage.factory import StorageFactory

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Inicializamos el cliente (Chroma o AWS OpenSearch)
    provider = VectorStoreFactory.get_provider()
    app.state.vector_store = provider.getVectorStore()
    app.state.record_manager = RecordManagerFactory.get_manager()
    app.state.llm_factory = LLMFactory
    
    # Manejador de contexto asíncrono para el checkpointer
    async with CheckpointerFactory.get_checkpointer() as checkpointer:
        app.state.checkpointer = checkpointer
        
        # Definir el modelo y las tools a usar en el grafo a traves del Registry
        tools = ToolRegistry.get_agent_tools(app.state.vector_store.as_retriever())
        
    # Compilamos el grafo UNA vez, pasándole el checkpointer de Postgres
    app.state.agent_service = AgentService(app.state.llm_factory, tools, app.state.checkpointer)
    
    # Ingestión providers (Status and Storage)
    app.state.status_provider = StatusProvider()
    app.state.storage_provider = StorageFactory.get_storage()
    
    yield
    # Shutdown: Limpieza de conexiones si fuera necesario
    # app.state.vector_store.close()

app = FastAPI(lifespan=lifespan)

# Asociar enrutador a la app principal
app.include_router(api_router, prefix="/api")
app.include_router(debug_router, prefix="/api")