from contextlib import asynccontextmanager
import os
import sys
import asyncio

# Configuración necesaria para psycopg3 en Windows antes de cualquier operación asíncrona
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI
import mlflow
from fastapi.middleware.cors import CORSMiddleware
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
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from prometheus_fastapi_instrumentator import Instrumentator
import os

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Inicializamos el cliente (Chroma o AWS OpenSearch)
    provider = VectorStoreFactory.get_provider()
    app.state.vector_store = provider.getVectorStore()
    app.state.record_manager = RecordManagerFactory.get_manager()
    app.state.llm_factory = LLMFactory
    
    # El checkpointer mantiene su context manager abierto durante toda la vida de la app
    async with CheckpointerFactory.get_checkpointer() as checkpointer:
        app.state.checkpointer = checkpointer
        
        # Registrar el vector store en el módulo de tools ANTES de compilar el grafo
        ToolRegistry.set_vector_store(app.state.vector_store)
        
        # Definir las tools a usar en el grafo a través del Registry
        tools = ToolRegistry.get_agent_tools()
        
        # Compilamos el grafo UNA vez, pasándole el checkpointer de Postgres
        app.state.agent_service = AgentService(app.state.llm_factory, tools, app.state.checkpointer)
        
        # Ingestión providers (Status and Storage)
        app.state.status_provider = StatusProvider()
        app.state.storage_provider = StorageFactory.get_storage()
        
        from src.providers.database.chat_provider import ChatProvider
        app.state.chat_provider = ChatProvider()
        
        yield
        # Shutdown: cerramos el pool del checkpointer
        await CheckpointerFactory.close_pool()

# Configuración de OpenTelemetry (Solo si se provee el endpoint)
otel_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
if otel_endpoint:
    # 1. Configurar Trazas
    provider = TracerProvider()
    processor = BatchSpanProcessor(OTLPSpanExporter(endpoint=otel_endpoint, insecure=True))
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)

    # 2. Configurar Métricas
    metric_reader = PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=otel_endpoint, insecure=True))
    metric_provider = MeterProvider(metric_readers=[metric_reader])
    metrics.set_meter_provider(metric_provider)

app = FastAPI(lifespan=lifespan)

# Configuración de MLflow
# --- CONFIGURACIÓN DE OBSERVABILIDAD (MLflow) ---
mlflow_uri = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow-service.personal-ai.svc.cluster.local:5000")
mlflow.set_tracking_uri(mlflow_uri)
mlflow.set_experiment("bmo_production_rag")

# Autolog DEBE ir antes de cualquier invocación de LangChain
mlflow.langchain.autolog(
    log_models=False,
    log_traces=True
)

# Test de conectividad al arrancar
try:
    with mlflow.start_run(run_name="api_startup_test"):
        mlflow.log_param("status", "startup")
        print(f" MLflow conectado exitosamente a {mlflow_uri}")
except Exception as e:
    print(f" Error conectando a MLflow: {e}")

# Instrumentar FastAPI y Celery tras instanciar el app
if otel_endpoint:
    from opentelemetry.instrumentation.celery import CeleryInstrumentor
    FastAPIInstrumentor.instrument_app(app)
    CeleryInstrumentor().instrument()  # Sella los mensajes hacia Celery con el Trace ID

# 3. Métricas para Prometheus (Endpoint /metrics)
Instrumentator().instrument(app).expose(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permite peticiones desde cualquier origen (ideal para desarrollo local)
    allow_credentials=True,
    allow_methods=["*"],  # Permite todos los métodos (POST, GET, y crucialmente OPTIONS)
    allow_headers=["*"],  # Permite todos los headers (como Content-Type)
)

# Asociar enrutador a la app principal
app.include_router(api_router, prefix="/api")
app.include_router(debug_router, prefix="/api")