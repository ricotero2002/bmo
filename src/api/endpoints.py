from fastapi import APIRouter, UploadFile, File, Depends
from src.api.schemas import QueryRequest, QueryResponse
from src.api.dependencies import get_vector_db, get_embeddings
from PyPDF2 import PdfReader
import io
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

#ver como exportar el router para main
router = APIRouter()

#esto tengo que acmodarlo bien
@router.post("/ingest")
async def ingest_pdf(
    file: UploadFile = File(...),
    db = Depends(get_vector_db),
    embedder = Depends(get_embeddings)
):
    # 1. Leer PDF (Byte stream)
    content = await file.read()
    pdf_file = io.BytesIO(content)
    
    # 2. Leer el PDF con PyPDF2
    reader = PdfReader(pdf_file)
    text = ""
    for page in reader.pages:
        if page.extract_text():
            text += page.extract_text() + "\n"
        
    # Crear un documento de Langchain
    document = Document(page_content=text, metadata={"source": file.filename})

    # 3. Chunking (RecursiveCharacterTextSplitter)
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = text_splitter.split_documents([document])
    
    # 4. Guardar en Vector Store
    db.add_documents(documents=chunks)
    
    return {"status": "success", "filename": file.filename}



@router.post("/query", response_model=QueryResponse)
async def query_rag(
    request: QueryRequest,
    db = Depends(get_vector_db),
    embedder = Depends(get_embeddings)
):
    # 1. Recuperar contexto (db.similarity_search)
    const results = await db.similaritySearch(request, 6);
    # 2. Generar respuesta con LLM
    return {"context": results}
