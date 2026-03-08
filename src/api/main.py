from contextlib import asynccontextmanager
from fastapi import FastAPI
from src.providers.vector_store.factory import VectorStoreFactory
from src.providers.record_manager.factory import RecordManagerFactory
from src.core.agent import AgentFactory
from src.api.endpoints import router as api_router
from src.api.debug import router as debug_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Inicializamos el cliente (Chroma o AWS OpenSearch)
    provider = VectorStoreFactory.get_provider()
    app.state.vector_store = provider.getVectorStore()
    app.state.record_manager = RecordManagerFactory.get_manager()
    app.state.agent_factory = AgentFactory
    yield
    # Shutdown: Limpieza de conexiones si fuera necesario
    # app.state.vector_store.close()

app = FastAPI(lifespan=lifespan)

# Asociar enrutador a la app principal
app.include_router(api_router, prefix="/api")
app.include_router(debug_router, prefix="/api")