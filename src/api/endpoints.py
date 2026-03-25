from fastapi import APIRouter, UploadFile, File, Depends
from src.schemas.fastapi import QueryRequest, QueryResponse, AskRequest, DeleteRequest
from src.api.dependencies import *
from celery.result import AsyncResult
from src.workers.celery_app import celery_app
import uuid
from typing import Optional, List
from fastapi.responses import StreamingResponse
import json


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

@router.post("/delete_file")
async def delete_document(
    request: DeleteRequest,
    status_provider = Depends(get_status_provider),
    get_deleting = Depends(get_deleting)
):
    """Encola la eliminación de un documento en la DB, Vector Store y Storage."""
    try:
        document_uuid = uuid.UUID(request.doc_id)
        job = status_provider.get_job(document_uuid)
        if not job:
            return {"error": "Job not found", "status_code": 404}

        result = await get_deleting.delete_file(
            doc_id=document_uuid,
            user_id=request.user_id,
        )
        return result
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



@router.post("/ask/stream")
async def ask_agent_stream(
    request: AskRequest,
    agent_service = Depends(get_agent_service)
):
    """
    Endpoint de streaming. Emite estados (status) y tokens (text) en tiempo real
    usando Server-Sent Events (SSE).
    """
    async def event_generator():
        try:
            user_context = request.user_info or {}
            
            # Llamamos al nuevo método asíncrono que creamos en agent.py
            async for event in agent_service.astream_chat(
                message=request.message, 
                thread_id=request.thread_id,
                user_info=user_context,
                prompt_version=request.prompt_version
            ):
                kind = event["event"]
                
                # 1. Detectar cuando el LLM está transmitiendo la respuesta final
                if kind == "on_chat_model_stream":
                    # Solo emitir tokens si fueron generados por el nodo principal del agente
                    if event.get("metadata", {}).get("langgraph_node") == "agent":
                        content = event["data"]["chunk"].content
                        if content:
                            # Enviamos tipo 'token' para que el frontend lo sume al chat
                            yield f"data: {json.dumps({'type': 'token', 'content': content})}\n\n"
                
                # 2. Detectar cuando se llama a una herramienta (Retriever)
                elif kind == "on_tool_start":
                    tool_name = event["name"]
                    if tool_name == "knowledge_base_retriever":
                        yield f"data: {json.dumps({'type': 'status', 'content': 'Buscando en la base de conocimientos...'})}\n\n"
                    else:
                        yield f"data: {json.dumps({'type': 'status', 'content': f'Usando herramienta: {tool_name}...'})}\n\n"
                
                # 3. Detectar nodos de validación (Guardrails/Graders)
                elif kind == "on_chain_start":
                    node_name = event.get("name")
                    if node_name == "grade_documents":
                        yield f"data: {json.dumps({'type': 'status', 'content': 'Evaluando relevancia de los documentos...'})}\n\n"
                    elif node_name == "grade_hallucinations":
                        yield f"data: {json.dumps({'type': 'status', 'content': 'Verificando alucinaciones...'})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
            
    # El media_type es crucial para que el frontend (ej. Vercel AI SDK) lo lea como un stream continuo
    return StreamingResponse(event_generator(), media_type="text/event-stream")

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