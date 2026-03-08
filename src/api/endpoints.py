from fastapi import APIRouter, UploadFile, File, Depends
from src.schemas.fastapi import QueryRequest, QueryResponse
from src.api.dependencies import get_vector_db, get_embeddings, get_record_manager, get_extraction_service, get_chunking_service, get_agent_factory
from langchain_core.documents import Document

#ver como exportar el router para main
router = APIRouter()

@router.post("/ingest")
async def ingest_document(
    file: UploadFile = File(...),
    db = Depends(get_vector_db),
    extraction_service = Depends(get_extraction_service), 
    record_manager = Depends(get_record_manager),
    chunking_service = Depends(get_chunking_service),
    agent_factory = Depends(get_agent_factory)
):
    # 1. Obtener contenido
    content = await file.read()
    
    # 2. Procesar (Uso del servicio)
    text = extraction_service.extract_text_from_bytes(content, file.filename)
    document = extraction_service.create_document(text, file.filename)

    # 3. Chunking (Router Adaptativo)
    chunks = chunking_service.process(document, agent_factory)
    
    # 4. Guardar
    result = extraction_service.index_documents(chunks, record_manager, db)
    
    return {
        "status": "success", 
        "filename": file.filename, 
        "chunks_created": len(chunks),
        "index_result": result
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
