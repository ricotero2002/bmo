from fastapi import APIRouter, Depends, Query, HTTPException
from typing import Optional
from src.api.dependencies import get_vector_db, get_status_provider, get_record_manager

router = APIRouter(prefix="/debug", tags=["Debug"])

@router.get("/documents")
async def get_documents(
    user_id: str = Query(..., description="ID del usuario para filtrar"),
    status_provider = Depends(get_status_provider)
):
    """
    Devuelve la lista de archivos (jobs) que han sido procesados o están en curso para un usuario.
    Consulta directamente la tabla de SQL 'ingestion_jobs'.
    """
    # Intentamos obtener los jobs filtrados por usuario
    # Como StatusProvider.get_all_jobs podría no existir, usamos una consulta directa o un método similar
    try:
        # Si StatusProvider no tiene un método genérico, buscamos por lo que sabemos que tiene
        # En este caso, asumimos que podemos consultar por usuario.
        from sqlalchemy import text
        with status_provider.engine.connect() as conn:
            query = text("SELECT doc_id, source_path, status, created_at, file_hash FROM ingestion_jobs WHERE user_id = :user_id ORDER BY created_at DESC")
            result = conn.execute(query, {"user_id": user_id})
            jobs = [dict(row._mapping) for row in result]
            
        return {
            "user_id": user_id,
            "total": len(jobs),
            "documents": jobs
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al listar documentos de SQL: {e}")

@router.get("/documents/{doc_id}/chunks")
async def get_document_chunks(
    doc_id: str, 
    db = Depends(get_vector_db),
    record_manager = Depends(get_record_manager)
):
    """
    Devuelve los chunks asociados a un UUID de documento específico.
    Usa el RecordManager para encontrar los IDs de Pinecone y luego los recupera.
    """
    # 1. Obtener los IDs de los chunks desde el RecordManager (Oracle)
    try:
        # list_keys devuelve los IDs (UUIDs) que se usaron en Pinecone
        pinecone_ids = record_manager.list_keys(group_ids=[doc_id])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al consultar RecordManager: {e}")

    if not pinecone_ids:
        return {
            "doc_id": doc_id,
            "total_chunks": 0,
            "chunks": [],
            "message": "No se encontraron chunks para este documento en el RecordManager."
        }

    # 2. Recuperar contenido y metadatos desde Pinecone
    chunks = []
    try:
        # PineconeVectorStore no tiene .get(), pero tiene ._index que es el SDK de Pinecone
        # El método fetch permite traer los vectores por ID
        if hasattr(db, "_index"):
            response = db._index.fetch(ids=pinecone_ids)
            
            # Pinecone SDK devuelve un objeto FetchResponse, no un dict.
            # Accedemos a .vectors que es un dict {id: Vector}
            vectors = getattr(response, "vectors", {})
            if not vectors and isinstance(response, dict):
                vectors = response.get("vectors", {})

            for p_id in pinecone_ids:
                vector_data = vectors.get(p_id)
                if vector_data:
                    # vector_data suele ser un objeto con atributo .metadata
                    metadata = getattr(vector_data, "metadata", {})
                    if not metadata and isinstance(vector_data, dict):
                        metadata = vector_data.get("metadata", {})
                        
                    chunks.append({
                        "id": p_id,
                        "content": metadata.get("text") or metadata.get("page_content") or "[Contenido no disponible en metadata]",
                        "metadata": metadata
                    })
        else:
            # Fallback si no es Pinecone (ej. Chroma local que SI tiene .get)
            result = db.get(ids=pinecone_ids, include=["metadatas", "documents"])
            docs = result.get("documents", [])
            metas = result.get("metadatas", [])
            for i in range(len(docs)):
                chunks.append({
                    "id": pinecone_ids[i],
                    "content": docs[i] if docs else None,
                    "metadata": metas[i] if i < len(metas) else {}
                })
    except Exception as e:
        # Si falla el fetch, al menos devolvemos los IDs
        return {
            "doc_id": doc_id,
            "total_chunks": len(pinecone_ids),
            "chunks_ids": pinecone_ids,
            "warning": f"No se pudo recuperar el contenido de los chunks: {e}"
        }
        
    return {
        "doc_id": doc_id,
        "total_chunks": len(chunks),
        "chunks": chunks
    }
