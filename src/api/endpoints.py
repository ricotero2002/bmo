from fastapi import APIRouter, UploadFile, File, Depends
from src.schemas.fastapi import QueryRequest, QueryResponse, AskRequest
from src.api.dependencies import *
from langchain_core.documents import Document
from src.workers.tasks import process_document_task
from celery.result import AsyncResult
from src.workers.celery_app import celery_app
import uuid
import io
from typing import Optional, List



#ver como exportar el router para main
router = APIRouter()

@router.get("/health")
async def health_check():
    return {"status": "ok", "message": "Personal AI Assistant API is running"}

@router.post("/ingest")
async def ingest_document(
    file: UploadFile = File(...),
    user_id: Optional[str] = None,
    orchestrator = Depends(get_orchestrator)
):
    """
    Endpoint robusto para la ingesta de documentos.
    Delega la orquestación (DB, Storage, Celery) al IngestionOrchestrator.
    """
    doc_id = uuid.uuid4()
    
    try:
        content = await file.read()
        result = await orchestrator.orchestrate_ingestion(
            doc_id=doc_id,
            filename=file.filename,
            content=content,
            user_id=user_id,
            metadata={"content_type": file.content_type}
        )
        
        return {
            **result,
            "filename": file.filename
        }
        
    except Exception as e:
        return {"error": f"Failed to initiate ingestion: {str(e)}", "status_code": 500}

@router.post("/ingest/batch")
async def ingest_batch(
    files: List[UploadFile] = File(...),
    user_id: Optional[str] = None,
    orchestrator = Depends(get_orchestrator)
):
    """
    Endpoint para ingesta masiva (Batch).
    Procesa múltiples archivos de forma secuencial delegando al orquestador.
    """
    results = []
    errors = []
    
    for file in files:
        doc_id = uuid.uuid4()
        try:
            content = await file.read()
            # Orquestar individualmente cada archivo
            res = await orchestrator.orchestrate_ingestion(
                doc_id=doc_id,
                filename=file.filename,
                content=content,
                user_id=user_id,
                metadata={"content_type": file.content_type, "batch": True}
            )
            results.append({**res, "filename": file.filename})
        except Exception as e:
            errors.append({"filename": file.filename, "error": str(e)})
            
    return {
        "status": "partial_success" if errors and results else ("success" if not errors else "failed"),
        "processed": results,
        "errors": errors
    }

@router.get("/ingestion-status/{doc_id}")
async def get_ingestion_status(
    doc_id: str,
    status_provider = Depends(get_status_provider)
):
    """Obtiene el estado detallado de la ingesta desde la DB SQL."""
    try:
        job_uuid = uuid.UUID(doc_id)
        job = status_provider.get_job(job_uuid)
        if not job:
            return {"error": "Job not found", "status_code": 404}
        return job
    except ValueError:
        return {"error": "Invalid UUID format", "status_code": 400}

@router.get("/task-status/{task_id}")
async def get_task_status(task_id: str):
    """Endpoint para monitorear el progreso de la ingesta."""
    res = AsyncResult(task_id, app=celery_app)
    return {
        "task_id": task_id,
        "status": res.status,
        "result": res.result if res.ready() else None
    }

@router.post("/query", response_model=QueryResponse)
async def query_rag(
    request: QueryRequest,
    db = Depends(get_vector_db),
    embedder = Depends(get_embeddings)
):
    # 1. Recuperar contexto (db.similarity_search) con filtro de usuario
    filter_opts = {}
    if request.user_id:
        filter_opts["user_id"] = request.user_id
        
    results = db.similarity_search(
        request.query, 
        k=6,
        filter=filter_opts if filter_opts else None
    )
    
    # Extraemos el contenido de los documentos encontrados
    context = [doc.page_content for doc in results] if results else []
    
    # 2. Generar respuesta con LLM
    return {"context": context}

@router.post("/ask")
async def ask_agent(
    request: AskRequest,
    agent_service = Depends(get_agent_service)
):
    try:
        # Llamamos al agente inyectándole el thread_id para continuar la charla en la DB
        # El user_id se puede pasar en user_info o como campo directo para filtrado RAG interno
        user_context = request.user_info or {}
        if request.user_id:
            user_context["user_id"] = request.user_id
            
        result = await agent_service.chat(
            message=request.message, 
            thread_id=request.thread_id,
            user_info=user_context,
            prompt_version=request.prompt_version
        )
        # Extraer el contenido generado para no devolver el resúmen del sistema
        generated_msg = result.get("generated")
        last_message = generated_msg.content if generated_msg else result["messages"][-1].content
        return {
            "response": last_message,
            "thread_id": request.thread_id
        }
    except Exception as e:
        return {"error": str(e), "status_code": 500}

@router.post("/dead-letter-queue-rabbit")
def check_dlq_health():
    """
    Endpoint manual para verificar si hay mensajes acumulados en la cola de errores de RabbitMQ.
    """
    try:
        with celery_app.connection() as conn:
            queue = conn.SimpleQueue("ingest_dlq")
            size = queue.qsize()
            return {
                "dlq_name": "ingest_dlq",
                "message_count": size,
                "status": "warning" if size > 10 else "ok"
            }
    except Exception as e:
        return {"error": str(e), "status_code": 500}