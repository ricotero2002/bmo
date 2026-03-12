from fastapi import APIRouter, UploadFile, File, Depends
from src.schemas.fastapi import QueryRequest, QueryResponse, AskRequest
from src.api.dependencies import get_vector_db, get_embeddings, get_record_manager, get_extraction_service, get_chunking_service, get_llm_factory,get_agent_service, get_status_provider, get_storage_provider
from langchain_core.documents import Document
from src.workers.tasks import process_document_task
from celery.result import AsyncResult
from src.workers.celery_app import celery_app
import uuid
import io
from typing import Optional



#ver como exportar el router para main
router = APIRouter()

@router.get("/health")
async def health_check():
    return {"status": "ok", "message": "Personal AI Assistant API is running"}

@router.post("/ingest")
async def ingest_document(
    file: UploadFile = File(...),
    user_id: Optional[str] = None,
    status_provider = Depends(get_status_provider),
    storage_provider = Depends(get_storage_provider)
):
    """
    Endpoint robusto para la ingesta de documentos.
    1. Crea registro en DB (status: received).
    2. Sube archivo a Object Storage (MinIO).
    3. Actualiza estado a 'queued'.
    4. Delega procesamiento al worker vía Celery.
    """
    doc_id = uuid.uuid4()
    
    try:
        # 1. Crear registro inicial en Postgres
        status_provider.create_job(
            doc_id=doc_id,
            user_id=user_id,
            source_path=file.filename,
            metadata={
                "filename": file.filename, 
                "content_type": file.content_type,
                "user_id": user_id,
                "uploaded_at": str(uuid.uuid1().time) # Example for date info if needed
            }
        )
        
        # 2. Subir a MinIO
        # El nombre del objeto incluirá el user_id para aislamiento si se desea,
        # pero el doc_id ya es único. Usaremos user_id como prefijo opcional.
        object_name = f"{user_id}/{doc_id}" if user_id else str(doc_id)
        
        content = await file.read()
        file_stream = io.BytesIO(content)
        storage_provider.upload_file(file_stream, object_name=object_name)
        
        # 3. Marcar como que ya está en cola
        status_provider.update_status(doc_id, "queued")
        
        # 4. Delegar al worker
        task = process_document_task.apply_async(
            kwargs={
                "doc_id": str(doc_id), 
                "filename": file.filename,
                "user_id": user_id,
                "object_name": object_name
            },
            task_id=str(doc_id),
            queue="ingest_q"
        )
        
        return {
            "status": "queued",
            "doc_id": str(doc_id),
            "filename": file.filename,
            "task_id": task.id
        }
        
    except Exception as e:
        # Si algo falla antes de encolar, intentamos marcar como fallido si llegamos a crear el registro
        try:
            status_provider.update_status(doc_id, "failed", error_msg=str(e))
        except:
            pass
        return {"error": f"Failed to initiate ingestion: {str(e)}", "status_code": 500}

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