import logging
import json
from datetime import date
from typing import Optional, Sequence, List

from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field
from langchain_core.documents import Document
from langchain_core.callbacks import Callbacks
# Import para el Compressor (ahora vive en langchain_core)
from langchain_core.documents import BaseDocumentCompressor

# Import para el Retriever (vive en langchain)
from langchain_classic.retrievers.contextual_compression import ContextualCompressionRetriever

from src.schemas.metadata import DocType, DOC_TYPES_INLINE
from src.core.llm import LLMFactory

logger = logging.getLogger(__name__)

# Referencia al vector store — se setea al inicio de la app via ToolRegistry.set_vector_store()
_vector_store = None

# Prefijo que identifica respuestas de error de la tool (para detección en el grafo)
TOOL_ERROR_PREFIX = "ERROR_TOOL:"


class GeminiReranker(BaseDocumentCompressor):
    """
    Usa el LLMFactory (Gemini) del proyecto para puntuar y reordenar 
    los documentos extraídos inicialmente por Pinecone.
    """
    k: int = 5
    
    def compress_documents(
        self,
        documents: Sequence[Document],
        query: str,
        callbacks: Optional[Callbacks] = None,
    ) -> Sequence[Document]:
        if not documents:
            return []
            
        # Usamos temperature=0 para que sea un juez estricto y determinista
        llm = LLMFactory.create().with_config({"temperature": 0.0})
        
        docs_text = ""
        for i, doc in enumerate(documents):
            # Limpiamos saltos de línea para que el prompt sea más compacto
            content_snippet = doc.page_content.replace("\n", " ")[:500]
            docs_text += f"--- Documento {i} ---\n{content_snippet}\n\n"
            
        prompt = f"""Eres un experto evaluador de relevancia de documentos.
Tu tarea es seleccionar los {self.k} documentos más relevantes para responder a la consulta del usuario.

Consulta: "{query}"

Documentos:
{docs_text}

Instrucciones:
1. Analiza cada documento y compáralo con la consulta.
2. Selecciona hasta {self.k} índices de los documentos más útiles.
3. Devuelve ÚNICAMENTE un array en formato JSON con los índices (números enteros) seleccionados, ordenados del más relevante al menos relevante.
Ejemplo de respuesta: [3, 0, 1]

Si ningún documento es relevante, devuelve []. No escribas explicaciones ni markdown."""
        
        try:
            response = llm.invoke(prompt)
            content = response.content.strip()
            
            # Limpiamos markdown si el LLM lo incluye por error
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
                
            indices = json.loads(content)
            
            reranked_docs = []
            for idx in indices:
                if 0 <= idx < len(documents):
                    reranked_docs.append(documents[idx])
            
            return reranked_docs[:self.k]
            
        except Exception as e:
            logger.error(f"Error en GeminiReranker: {e}")
            # Si falla el reranking, devolvemos los originales (seguridad)
            return documents[:self.k]


class RetrieverInput(BaseModel):
    query: str = Field(..., description="El texto o pregunta a buscar (requerido, NO puede estar vacío).")
    date_from: str = Field(default="", description="Fecha mínima de los documentos en formato ISO YYYY-MM-DD (opcional).")
    source_filter: str = Field(default="", description="Nombre exacto del archivo a filtrar (opcional).")
    doc_type: Optional[DocType] = Field(
        default=None, 
        description=f"Filtra por tipo de documento. Úsalo cuando el usuario sea específico. Valores: {DOC_TYPES_INLINE}."
    )
    k_results: int = Field(
        default=4,
        ge=2,
        le=7,
        description="Cantidad de resultados finales deseados. Usa 2-3 para respuestas rápidas, 5-7 para investigación profunda."
    )


def build_metadata_filter(
    date_from: Optional[str] = None,
    source_filter: Optional[str] = None,
    user_id: Optional[str] = None,
    doc_type: Optional[str] = None,
) -> Optional[dict]:
    """
    Construye un dict de filtros compatible con Pinecone/ChromaDB.
    """
    conditions = []

    if date_from:
        try:
            from datetime import datetime, timezone
            dt = datetime.fromisoformat(f"{date_from}T00:00:00+00:00")
            cutoff_ts = dt.timestamp()
            conditions.append({"created_at": {"$gte": cutoff_ts}})
        except Exception:
            logger.warning(f"date_from inválido ignorado: '{date_from}'")

    if source_filter:
        conditions.append({"source": {"$eq": source_filter}})

    if user_id:
        conditions.append({"user_id": {"$eq": user_id}})

    if doc_type:
        conditions.append({"doc_type": {"$eq": doc_type}})

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def _get_adjacent_chunks(source: str, center_index: int, user_id: str) -> str:
    """Busca los chunks N-1, N y N+1 de un mismo documento y los concatena."""
    if center_index is None or not source:
        return ""
    
    # Buscamos la ventana de chunks
    target_indices = [center_index - 1, center_index, center_index + 1]
    
    # Filtro estricto para asegurar que son del mismo archivo y usuario
    window_filter = {
        "$and": [
            {"user_id": {"$eq": user_id}},
            {"source": {"$eq": source}},
            {"chunk_index": {"$in": target_indices}}
        ]
    }
    
    try:
        # Buscamos en el vector store (k=3 porque son 3 chunks máximo)
        # Usamos "" como query porque queremos búsqueda pura por filtro de metadata
        docs = _vector_store.similarity_search("", k=3, filter=window_filter)
        
        if not docs:
            return ""
            
        # Ordenamos por índice real para que el texto tenga sentido secuencial
        docs.sort(key=lambda d: d.metadata.get("chunk_index", 0))
        
        return "\n".join([d.page_content for d in docs])
    except Exception as e:
        logger.warning(f"Error recuperando chunks adyacentes: {e}")
        return ""


@tool(args_schema=RetrieverInput)
def knowledge_base_retriever(
    query: str,
    date_from: str = "",
    source_filter: str = "",
    doc_type: str = "",
    k_results: int = 4,
    config: RunnableConfig = None,
) -> str:
    """
    Busca y recupera información relevante de la base de conocimientos personal del usuario.
    Utiliza Re-Ranking y expansión de contexto (Sliding Window) para máxima precisión.
    """
    user_id = config.get("configurable", {}).get("user_id") if config else None

    # Validar query
    if not query or not query.strip():
        return f"{TOOL_ERROR_PREFIX} la query no puede estar vacía."

    if _vector_store is None:
        logger.error("knowledge_base_retriever: vector_store no inicializado.")
        return f"{TOOL_ERROR_PREFIX} la base de conocimientos no está disponible."

    metadata_filter = build_metadata_filter(
        date_from=date_from or None,
        source_filter=source_filter or None,
        user_id=user_id,
        doc_type=doc_type or None,
    )

    try:
        # 1. Configurar Re-Ranker
        reranker = GeminiReranker(k=k_results)
        
        # 2. Configurar Retriever con Compresión (Re-Ranking)
        # Pedimos 2.5 veces más resultados a Pinecone para que el Re-Ranker tenga de donde elegir
        base_retriever = _vector_store.as_retriever(
            search_kwargs={"k": int(k_results * 2.5), "filter": metadata_filter}
        )
        
        compression_retriever = ContextualCompressionRetriever(
            base_compressor=reranker,
            base_retriever=base_retriever
        )

        # 3. Ejecutar búsqueda + re-ranking
        docs = compression_retriever.invoke(query)
        
        # Fallback si no hay resultados con filtros
        if not docs and (date_from or source_filter or doc_type):
            fallback_filter = build_metadata_filter(user_id=user_id)
            base_retriever_fb = _vector_store.as_retriever(
                search_kwargs={"k": int(k_results * 2.5), "filter": fallback_filter}
            )
            compression_retriever_fb = ContextualCompressionRetriever(
                base_compressor=reranker,
                base_retriever=base_retriever_fb
            )
            docs = compression_retriever_fb.invoke(query)
            if docs:
                logger.info("Retriever: Fallback exitoso sin filtros específicos.")

        if not docs:
            return "No encontré información relevante en la base de conocimientos."

        # 4. Expansión de Contexto (Adyacentes)
        final_results = []
        processed_blobs = set() # Para evitar duplicados en expansión

        for doc in docs:
            source = doc.metadata.get('source')
            idx = doc.metadata.get('chunk_index')
            chunk_type = doc.metadata.get('chunk_type', 'markdown')
            
            # ID único para este bloque de contexto
            blob_id = f"{source}_{idx}"
            if blob_id in processed_blobs:
                continue
                
            # Solo expandimos si no es agentic (regla de precisión)
            if chunk_type != "agentic" and idx is not None:
                expanded_text = _get_adjacent_chunks(source, idx, user_id)
                content = expanded_text if expanded_text else doc.page_content
            else:
                content = doc.page_content
                
            final_results.append(
                f"[Fuente: {source or 'desconocida'} | Tipo: {doc.metadata.get('doc_type', 'general')}]\n{content}"
            )
            processed_blobs.add(blob_id)

        return "\n\n---\n\n".join(final_results)

    except Exception as e:
        logger.error(f"Error en knowledge_base_retriever: {e}")
        return f"{TOOL_ERROR_PREFIX} {str(e)}"
