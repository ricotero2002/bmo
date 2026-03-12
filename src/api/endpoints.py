from fastapi import APIRouter, UploadFile, File, Depends
from src.schemas.fastapi import QueryRequest, QueryResponse, AskRequest
from src.api.dependencies import get_vector_db, get_embeddings, get_record_manager, get_extraction_service, get_chunking_service, get_llm_factory,get_agent_service
from langchain_core.documents import Document
from src.workers.tasks import process_document_task
from celery.result import AsyncResult
from src.workers.celery_app import celery_app
import uuid


#ver como exportar el router para main
router = APIRouter()

@router.post("/ingest")
async def ingest_document(
    file: UploadFile = File(...),
):
    # 1. Obtener contenido
    content = await file.read()
    
    # 2. Codificar a base64 para envío seguro vía Celery (JSON compatible)
    import base64
    content_b64 = base64.b64encode(content).decode('utf-8')
    
    # 3. Delegar al worker
    task_id = str(uuid.uuid4())
    task = process_document_task.apply_async(
        args=[content_b64, file.filename],
        task_id=task_id
    )
    
    return {
        "status": "queued", 
        "filename": file.filename, 
        "task_id": task.id
    }

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
    # 1. Recuperar contexto (db.similarity_search)
    results = db.similarity_search(request.query, k=6)
    
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
        result = await agent_service.chat(
            message=request.message, 
            thread_id=request.thread_id,
            user_info=request.user_info,
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