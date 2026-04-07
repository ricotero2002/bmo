from fastapi import APIRouter, Depends, Query, HTTPException
from typing import Optional
from src.api.dependencies import get_vector_db, get_status_provider, get_record_manager

router = APIRouter(prefix="/debug", tags=["Debug"])

@router.get("/document")
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

# get_document_chunks ha sido movido a endpoints.py para centralizar la lógica.
