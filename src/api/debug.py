from fastapi import APIRouter, Depends
from src.api.dependencies import get_vector_db

router = APIRouter(prefix="/debug", tags=["Debug"])

@router.get("/documents")
async def get_documents(db = Depends(get_vector_db)):
    """
    Devuelve la lista de archivos (documents) únicos que han sido indexados.
    Extrae la información directamente de los metadatos de la Vector Database.
    """
    # Obtenemos solo los metadatos de toda la base de datos vectorial
    result = db.get(include=["metadatas"])
    
    sources = set()
    for meta in result.get("metadatas", []):
        if meta and "source" in meta:
            sources.add(meta["source"])
            
    return {"documents": list(sources)}

@router.get("/documents/{filename}/chunks")
async def get_document_chunks(filename: str, db = Depends(get_vector_db)):
    """
    Devuelve los chunks asociados a un nombre de archivo (source) específico.
    Permite visualizar cómo se fragmentó el archivo y qué metadatos tiene cada chunk.
    """
    # Filtramos en Chroma por el metadato 'source'
    result = db.get(where={"source": filename}, include=["metadatas", "documents"])
    
    chunks = []
    docs = result.get("documents", [])
    metas = result.get("metadatas", [])
    ids = result.get("ids", [])
    
    for i in range(len(docs)):
        chunks.append({
            "id": ids[i] if i < len(ids) else None,
            "content": docs[i] if docs else None,
            "metadata": metas[i] if i < len(metas) else {}
        })
        
    return {
        "filename": filename,
        "total_chunks": len(chunks),
        "chunks": chunks
    }
