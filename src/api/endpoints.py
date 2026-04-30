from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, Header
from fastapi.responses import StreamingResponse, JSONResponse
from src.schemas.fastapi import QueryRequest, QueryResponse, AskRequest, DeleteRequest, FeedbackRequest, TriggerIngestionRequest
from src.api.dependencies import *
from celery.result import AsyncResult
from src.workers.celery_app import celery_app
from langchain_core.messages import AIMessage
import uuid
from typing import Optional, List
from starlette.background import BackgroundTask
import json
import asyncio

#ver como exportar el router para main
router = APIRouter()

# --- EL PATOVICA ASÍNCRONO ---
# Permitimos un máximo de 10 ejecuciones pesadas (LLM) en paralelo por cada Worker.
# Esto evita picos de RAM (>2GB) pero permite que las peticiones esperen en fila en vez de dar 503.
llm_semaphore = asyncio.Semaphore(30)

@router.get("/health")
async def health_check():
    return {"status": "ok", "message": "Personal AI Assistant API is running"}



# --- EL ENDPOINT PROTEGIDO ---
@router.get("/seguro")
async def endpoint_protegido(user_payload: dict = Depends(verify_token)):
    user_id = user_payload.get("sub")
    # Si ves esto, significa que el token es 100% real y válido
    return {
        "mensaje": "¡Éxito! BMO te reconoce.",
        "tu_id_auth0": user_id,
        "payload_completo": user_payload
    }

@router.post("/ingest")
async def ingest_document(
    file: UploadFile = File(...),
    user_id: Optional[str] = Form(None),
    document_date: Optional[str] = Form(None),
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
            metadata={
                "content_type": file.content_type,
                "document_date": document_date
            }
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
    user_id: Optional[str] = Form(None),
    document_date: Optional[str] = Form(None),
    orchestrator = Depends(get_orchestrator)
):
    """
    Endpoint para ingesta masiva (Batch).
    Procesa múltiples archivos de forma secuencial delegando al orquestador.
    """
    results = []
    errors = []
    
    batch_uuid = uuid.uuid4()
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
                metadata={
                    "content_type": file.content_type, 
                    "batch": True,
                    "document_date": document_date
                },
                batch_id=batch_uuid
            )
            results.append({**res, "filename": file.filename})
        except Exception as e:
            errors.append({"filename": file.filename, "error": str(e)})
            
    final_status = "partial_success" if errors and results else ("success" if not errors else "failed")
    
    status_provider = orchestrator.status_provider
    doc_ids = [res.get("doc_id") for res in results if res.get("doc_id")]
    status_provider.save_batch_info(
        batch_id=batch_uuid,
        user_id=user_id,
        status=final_status,
        total_files=len(files),
        doc_ids=doc_ids,
        errors=errors
    )
            
    return {
        "status": final_status,
        "batch_id": str(batch_uuid),
        "processed": results,
        "errors": errors
    }

@router.post("/ingest/trigger")
async def trigger_ingestion(
    request: TriggerIngestionRequest,
    orchestrator = Depends(get_orchestrator)
):
    """
    Endpoint para disparar la ingesta de archivos que ya se encuentran en el Storage (ej. MinIO).
    Usado principalmente por Airflow/Background Workers para el patrón Claim-Check.
    """
    results = []
    errors = []
    
    batch_uuid = uuid.UUID(request.batch_id) if request.batch_id else uuid.uuid4()
    
    for file_info in request.files:
        doc_id = uuid.uuid4()
        try:
            # Llamamos al orquestador sin "content", por ende NO subirá a MinIO de nuevo,
            # solo creará el job en Postgres y encolará en Celery usando el object_name.
            res = await orchestrator.orchestrate_ingestion(
                doc_id=doc_id,
                filename=file_info.filename,
                content=None,
                user_id=request.user_id,
                object_name=file_info.object_name,
                metadata=file_info.metadata,
                batch_id=batch_uuid,
                file_hash=file_info.file_hash
            )
            # Si ya existía y está processado, el orquestador retorna "already_exists" en res["status"]
            results.append({**res, "filename": file_info.filename})
        except Exception as e:
            errors.append({"filename": file_info.filename, "error": str(e)})
            
    final_status = "partial_success" if errors and results else ("success" if not errors else "failed")
    
    # Obtener el status_provider del orquestador u obtenerlo por dependencia
    status_provider = orchestrator.status_provider
    doc_ids = [res.get("doc_id") for res in results if res.get("doc_id")]
    status_provider.save_batch_info(
        batch_id=batch_uuid,
        user_id=request.user_id,
        status=final_status,
        total_files=len(request.files),
        doc_ids=doc_ids,
        errors=errors
    )
            
    return {
        "status": final_status,
        "batch_id": str(batch_uuid),
        "processed": results,
        "errors": errors
    }

@router.get("/ingestion-status/batch/{batch_id}")
async def get_batch_status_details(
    batch_id: str,
    status_provider = Depends(get_status_provider)
):
    """Obtiene el estado detallado de un batch de ingesta."""
    try:
        batch_uuid = uuid.UUID(batch_id)
        batch_details = status_provider.get_batch_details(batch_uuid)
        if not batch_details:
            return {"error": "Batch not found", "status_code": 404}
        return batch_details
    except ValueError:
        return {"error": "Invalid UUID format", "status_code": 400}

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

@router.get("/debug/document/{doc_id}/chunks")
async def get_document_chunks(
    doc_id: str,
    db = Depends(get_vector_db),
    record_manager = Depends(get_record_manager)
):
    """Lista los chunks insertados en la base Vectorial por doc_id"""
    try:
        # 1. Intentamos usar RecordManager para obtener IDs específicos si el db no tiene get() fácil
        # Esto es vital para Pinecone (GeminiEmbedder falla con empty search "")
        pinecone_ids = []
        try:
            pinecone_ids = record_manager.list_keys(group_ids=[doc_id])
        except Exception as e:
            print(f"RecordManager not available or failed: {e}")

        # 2. Si tenemos IDs, los recuperamos directamente
        if pinecone_ids:
            chunks = []
            # Pinecone VectorStore
            if hasattr(db, "_index"):
                response = db._index.fetch(ids=pinecone_ids)
                vectors = getattr(response, "vectors", {})
                for p_id in pinecone_ids:
                    vector_data = vectors.get(p_id)
                    if vector_data:
                        metadata = getattr(vector_data, "metadata", {})
                        chunks.append({
                            "id": p_id,
                            "page_content": metadata.get("text") or metadata.get("page_content") or "",
                            "metadata": metadata
                        })
                return {"chunks": chunks, "total_chunks": len(chunks), "doc_id": doc_id}
            
            # Chroma or generic .get()
            elif hasattr(db, "get"):
                res = db.get(ids=pinecone_ids, include=["metadatas", "documents"])
                docs = res.get("documents", [])
                metas = res.get("metadatas", [])
                for i in range(len(docs)):
                    chunks.append({
                        "id": pinecone_ids[i],
                        "page_content": docs[i] if docs else "",
                        "metadata": metas[i] if i < len(metas) else {}
                    })
                return {"chunks": chunks, "total_chunks": len(chunks), "doc_id": doc_id}

        # 3. Fallback: Si NO tenemos IDs de RecordManager, intentamos el .get() directo por filtro (Chroma)
        if hasattr(db, "_collection"):
            res = db._collection.get(where={"doc_id": doc_id})
            chunks = []
            if res and "ids" in res:
                for i in range(len(res["ids"])):
                    chunks.append({
                        "id": res["ids"][i],
                        "page_content": res["documents"][i] if "documents" in res and res["documents"] else "",
                        "metadata": res["metadatas"][i] if "metadatas" in res and res["metadatas"] else {}
                    })
            return {"chunks": chunks, "total_chunks": len(chunks), "doc_id": doc_id}

        # 4. Si todo lo anterior falla, no hacemos similarity_search("") para evitar crash de Gemini
        return {
            "chunks": [],
            "total_chunks": 0,
            "doc_id": doc_id,
            "message": "No se pudieron recuperar chunks. Use RecordManager IDs o Chroma."
        }
    except Exception as e:
        return {"error": str(e), "status_code": 500}

@router.get("/debug/document")
async def list_documents(
    user_id: str,
    status_provider = Depends(get_status_provider)
):
    """Lista todos los documentos ingeridos para un usuario específico (para depuración)."""
    try:
        # Usamos el engine de status_provider para hacer una consulta directa
        from sqlalchemy import text
        query = text("SELECT doc_id, source_path, status, created_at, file_hash FROM ingestion_jobs WHERE user_id = :user_id ORDER BY created_at DESC")
        
        with status_provider.engine.connect() as conn:
            result = conn.execute(query, {"user_id": user_id})
            # Convertimos a lista de diccionarios
            documents = []
            for row in result:
                # row es un objeto que soporta mapeo si es SQLAlchemy 2.0+ o tiene _mapping
                r = row._mapping if hasattr(row, "_mapping") else dict(row)
                documents.append(dict(r))
                
        return {
            "user_id": user_id,
            "documents": documents,
            "total": len(documents)
        }
    except Exception as e:
        return {"error": str(e), "status_code": 500}

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

        # O si el documento aparece distinto que indexed

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
    import logging
    from src.tools.metadata_filter import build_metadata_filter
    logger = logging.getLogger(__name__)

    # 1. Recuperar contexto (db.similarity_search) con filtro de usuario
    filter_opts = build_metadata_filter(user_id=request.user_id)
        
    logger.info(f"[/query] Ejecutando búsqueda semántica: '{request.query}' (Filtros: {filter_opts})")
    
    try:
        results = db.similarity_search(
            request.query, 
            k=3,
            filter=filter_opts if filter_opts else None
        )
        
        logger.info(f"[/query] Se encontraron {len(results)} documentos.")
        for i, doc in enumerate(results):
            logger.debug(f"[/query] Doc {i+1} Metadatos: {doc.metadata}")

        # Extraemos el contenido de los documentos encontrados
        context = [doc.page_content for doc in results] if results else []
        
        # 2. Generar respuesta con LLM
        return {"context": context}
    except Exception as e:
        logger.error(f"[/query] Error en búsqueda semántica: {e}")
        return {"context": [], "error": str(e)}


@router.post("/ask")
async def ask_agent(
    request: AskRequest,
    x_stress_test: Optional[bool] = Header(None, alias="X-Stress-Test"),
    agent_service = Depends(get_agent_service)
):
    try:
        # Si thread_id está vacío, creamos una nueva conversación
        thread_id = request.thread_id or str(uuid.uuid4())
        user_context = request.user_info or {}
        
        # Inyectar el flag de stress test si el header está presente
        if x_stress_test:
            user_context["is_stress_test"] = True

        async with llm_semaphore:
            result = await agent_service.chat(
                message=request.message,
                thread_id=thread_id,
                user_info=user_context,
                prompt_version=request.prompt_version
            )
        # Obtener el último mensaje de IA
        messages = result.get("messages", [])
        last_message = ""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) or (hasattr(msg, "type") and msg.type == "ai"):
                last_message = msg.content
                break
        
        # Si no se encontró AIMessage, usar el último mensaje en general
        if not last_message and messages:
            last_message = messages[-1].content
        return JSONResponse(
            content={
                "response": last_message,
                "thread_id": thread_id
            },
            headers={"X-Thread-ID": thread_id}
        )
    except Exception as e:
        return {"error": str(e), "status_code": 500}



@router.get("/chats")
async def get_chats(
    user_id: str,
    chat_provider = Depends(get_chat_provider)
):
    """
    Obtiene la lista de conversaciones (hilos) para un usuario.
    """
    try:
        chats = chat_provider.get_user_chats(user_id)
        return {"chats": chats}
    except Exception as e:
        return {"error": str(e), "status_code": 500}

@router.get("/chats/{thread_id}/messages")
async def get_messages(
    thread_id: str,
    chat_provider = Depends(get_chat_provider)
):
    """
    Obtiene todos los mensajes de un hilo específico.
    """
    try:
        thread_uuid = uuid.UUID(thread_id)
        messages = chat_provider.get_chat_messages(thread_uuid)
        return {"messages": messages}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid thread_id format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ask/stream")
async def ask_agent_stream(
    request: AskRequest,
    x_stress_test: Optional[bool] = Header(None, alias="X-Stress-Test"),
    agent_service = Depends(get_agent_service),
    chat_provider = Depends(get_chat_provider)
):
    """
    Endpoint de streaming. Emite estados (status) y tokens (text) en tiempo real
    usando Server-Sent Events (SSE). Guarda la conversión en la BD de forma asíncrona.
    """
    thread_id = request.thread_id or str(uuid.uuid4())
    full_response_text = []

    async def event_generator():
        # Informar al frontend de inmediato el ID del thread por si fue generado nuevo
        yield f"data: {json.dumps({'type': 'thread_id', 'content': thread_id})}\n\n"
        
        try:
            user_context = request.user_info or {}
            if x_stress_test:
                user_context["is_stress_test"] = True
            
            # MAGIA AQUÍ: Entramos a la sala de espera (Semáforo).
            # Solo avanzará si hay menos de 10 peticiones procesándose en este worker.
            async with llm_semaphore:
                async for event in agent_service.astream_chat(
                    message=request.message,
                    thread_id=thread_id,
                    user_info=user_context,
                    prompt_version=request.prompt_version
                ):
                    kind = event["event"]
                    tags = event.get("tags", [])

                    if kind == "on_chat_model_start" and "agent_generation" in tags:
                        # Protección contra errores de tipo en la persistencia
                        current_response = "".join(str(item) for item in full_response_text)
                        if current_response.strip():
                            yield f"data: {json.dumps({'type': 'status', 'content': 'Corrigiendo imprecisiones detectadas...'})}\n\n"
                        full_response_text.clear()

                    # --- FIX: CAPTURA DEL PLAN DE EJECUCIÓN ---
                    elif kind == "on_chain_end" and event.get("name") == "task_planner":
                        output = event.get("data", {}).get("output", {})
                        if isinstance(output, dict) and "task_plan" in output:
                            yield f"data: {json.dumps({'type': 'plan', 'data': output['task_plan']})}\n\n"

                    elif kind == "on_chat_model_stream" and "agent_generation" in tags:
                        content = event["data"]["chunk"].content
                        if content:
                            # Aseguramos que content sea string (puede ser lista en modelos multimodales/v2)
                            if isinstance(content, list):
                                content = "".join(str(c.get("text", c)) if isinstance(c, dict) else str(c) for c in content)

                            full_response_text.append(str(content))
                            yield f"data: {json.dumps({'type': 'token', 'content': str(content)})}\n\n"

                    # --- FIX: CAPTURA DE INPUTS DE LA HERRAMIENTA (Para Status detallado) ---
                    elif kind == "on_tool_start":
                        tool_name = event["name"]
                        tool_input = event.get("data", {}).get("input", {})
                        yield f"data: {json.dumps({'type': 'tool-start', 'data': tool_name, 'input': tool_input})}\n\n"

                    elif kind == "on_tool_end":
                        tool_name = event["name"]
                        yield f"data: {json.dumps({'type': 'tool-end', 'data': tool_name})}\n\n"

                    elif kind == "on_chain_start":
                        node_name = event.get("name")
                        if node_name == "grade_documents":
                            yield f"data: {json.dumps({'type': 'status', 'content': 'Evaluando relevancia de los documentos...'})}\n\n"
                        elif node_name == "grade_hallucinations":
                            yield f"data: {json.dumps({'type': 'status', 'content': 'Verificando alucinaciones...'})}\n\n"

        except asyncio.CancelledError:
            import logging
            logging.getLogger(__name__).error("[CRÍTICO] El stream fue cancelado (timeout de red o cliente desconectado). LangGraph se interrumpió silenciosamente.")
            # Yielding a final explicit error is useless if the connection is dead, but we log and re-raise
            raise
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
            
        finally:
            # Sincronizamos el final del stream
            try:
                # Crear la cabecera del chat si no existe
                title = request.message[:50] + "..." if len(request.message) > 50 else request.message
                user_id = request.user_info.get("user_id", "anonymous") if request.user_info else "anonymous"
                thread_uuid = uuid.UUID(thread_id)
                
                chat_provider.create_chat(user_id=user_id, title=title, thread_id=thread_uuid)
                
                # Guardar mensaje del usuario
                chat_provider.add_message(thread_id=thread_uuid, role="user", content=request.message)
                
                # Guardar respuesta generada completa
                generated_text = "".join(full_response_text)
                if generated_text:
                    chat_provider.add_message(thread_id=thread_uuid, role="assistant", content=generated_text)
            except Exception as e:
                print(f"[CHAT_PERSISTENCE_ERROR] {e}")

    # El media_type es crucial para que el frontend (ej. Vercel AI SDK) lo lea como un stream continuo
    return StreamingResponse(
        event_generator(), 
        media_type="text/event-stream", 

        headers={"X-Thread-ID": thread_id}
    )

@router.delete("/chats/{thread_id}")
async def delete_chat(
    thread_id: str,
    chat_provider = Depends(get_chat_provider)
):
    """
    Elimina un chat (hilo), todos sus mensajes y sus checkpoints de LangGraph.
    """
    try:
        thread_uuid = uuid.UUID(thread_id)
        
        # 1. Eliminar de la base de datos relacional (chats y mensajes)
        if hasattr(chat_provider, "delete_chat"):
            chat_provider.delete_chat(thread_uuid)
        else:
            print("chat_provider doesn't have delete_chat implemented.")
            
        # 2. Eliminar checkpoints de PostgreSQL (Aiven)
        import os
        uri = os.getenv("AIVEN_PG_URI")
        if uri:
            from psycopg import AsyncConnection
            async with await AsyncConnection.connect(uri) as conn:
                async with conn.cursor() as cur:
                    await cur.execute("DELETE FROM checkpoints WHERE thread_id = %s", (str(thread_uuid),))
                    await cur.execute("DELETE FROM checkpoint_blobs WHERE thread_id = %s", (str(thread_uuid),))
                    await cur.execute("DELETE FROM checkpoint_writes WHERE thread_id = %s", (str(thread_uuid),))
                    await conn.commit()
            
        return {"status": "success", "message": f"Chat {thread_id} y sus checkpoints eliminados."}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid thread_id format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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

@router.get("/feedback")
async def get_feedback(
    limit: int = 100,
    chat_provider = Depends(get_chat_provider)
):
    """
    Lista los últimos feedbacks recibidos (Thumbs up/down).
    """
    try:
        feedbacks = chat_provider.get_all_feedback(limit=limit)
        return {"feedbacks": feedbacks}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving feedback: {str(e)}")

@router.post("/feedback")
async def receive_feedback(
    request: FeedbackRequest,
    chat_provider = Depends(get_chat_provider)
):
    """
    Endpoint para recibir retroalimentación del usuario (Thumbs Up/Down).
    Guarda en la base de datos la interacción y posible corrección.
    """
    try:
        if not hasattr(chat_provider, "add_chat_feedback"):
            raise HTTPException(status_code=500, detail="chat_provider missing add_chat_feedback")
            
        feedback_id = chat_provider.add_chat_feedback(
            thread_id=request.thread_id,
            score=request.score,
            message_id=request.message_id,
            user_prompt=request.user_prompt,
            ai_response=request.ai_response,
            tools_used=request.tools_used,
            user_correction=request.user_correction
        )
        return {"status": "success", "feedback_id": str(feedback_id)}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Feedback error: {str(e)}")