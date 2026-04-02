import logging
from datetime import date
from typing import Optional

from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field
from src.schemas.metadata import DocType, DOC_TYPES_INLINE

logger = logging.getLogger(__name__)

# Referencia al vector store — se setea al inicio de la app via ToolRegistry.set_vector_store()
_vector_store = None

# Prefijo que identifica respuestas de error de la tool (para detección en el grafo)
TOOL_ERROR_PREFIX = "ERROR_TOOL:"

class RetrieverInput(BaseModel):
    query: str = Field(..., description="El texto o pregunta a buscar (requerido, NO puede estar vacío).")
    date_from: str = Field(default="", description="Fecha mínima de los documentos en formato ISO YYYY-MM-DD (opcional).")
    source_filter: str = Field(default="", description="Nombre exacto del archivo a filtrar (opcional).")
    doc_type: Optional[DocType] = Field(
        default=None, 
        description=f"Filtra por tipo de documento. Úsalo cuando el usuario sea específico. Valores: {DOC_TYPES_INLINE}."
    )


def build_metadata_filter(
    date_from: Optional[str] = None,
    source_filter: Optional[str] = None,
    user_id: Optional[str] = None,
    doc_type: Optional[str] = None,
) -> Optional[dict]:
    """
    Construye un dict de filtros compatible con ChromaDB / OpenSearch.
    Sintaxis: {"$and": [{"campo": {"$op": valor}}, ...]}
    """
    conditions = []

    if date_from:
        # ChromaDB requiere un Unix timestamp numérico (float) para operadores de comparación
        try:
            from datetime import datetime, timezone
            dt = datetime.fromisoformat(f"{date_from}T00:00:00+00:00")
            cutoff_ts = dt.timestamp()  # float, e.g. 1742342400.0
            conditions.append({"created_at": {"$gte": cutoff_ts}})
        except Exception:
            logger.warning(f"date_from inválido ignorado: '{date_from}'")

    if source_filter:
        conditions.append({"filename": {"$eq": source_filter}})

    if user_id:
        conditions.append({"user_id": {"$eq": user_id}})

    if doc_type:
        conditions.append({"doc_type": {"$eq": doc_type}})

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


@tool(args_schema=RetrieverInput)
def knowledge_base_retriever(
    query: str,
    date_from: str = "",
    source_filter: str = "",
    doc_type: str = "",
    config: RunnableConfig = None,
) -> str:
    """
    Busca y recupera información relevante de la base de conocimientos personal del usuario.

    Usá esta herramienta para CUALQUIER pregunta que requiera acceder a documentos,
    notas, reuniones, CVs u otra información personal almacenada.
    """
    # user_id se inyecta desde el config (invisible para el LLM)
    user_id = None
    if config:
        user_id = config.get("configurable", {}).get("user_id")

    # Validar que la query no esté vacía (causaría error de embedding en la API)
    if not query or not query.strip():
        return (
            f"{TOOL_ERROR_PREFIX} la query no puede estar vacía. "
            "Debes proporcionar una descripción de lo que estás buscando. "
            "Vuelve a llamar a esta herramienta con un parámetro 'query' significativo "
            "(por ejemplo: 'contenido del archivo', 'notas de la reunión')."
        )

    metadata_filter = build_metadata_filter(
        date_from=date_from or None,
        source_filter=source_filter or None,
        user_id=user_id,
        doc_type=doc_type or None,
    )

    if _vector_store is None:
        logger.error("knowledge_base_retriever: vector_store no inicializado.")
        return f"{TOOL_ERROR_PREFIX} la base de conocimientos no está disponible."

    try:
        # Intento 1: Búsqueda con todos los filtros
        docs = _vector_store.similarity_search(
            query,
            k=4,
            filter=metadata_filter,
        )
        
        # --- AUTO-FALLBACK ---
        # Si se usaron filtros (fecha, tipo, fuente) y se obtuvieron 0 resultados,
        # reintentamos sin esos filtros (solo con user_id para aislamiento)
        has_filters = bool(date_from or source_filter or doc_type)
        fallback_active = False

        if not docs and has_filters:
            logger.info("0 resultados con filtros específicos. Reintentando búsqueda pura sin filtros secundarios...")
            fallback_filter = build_metadata_filter(user_id=user_id)
            docs = _vector_store.similarity_search(
                query,
                k=4,
                filter=fallback_filter,
            )
            fallback_active = True
        # ---------------------

        logger.info(f"knowledge_base_retriever: docs finales encontrados={len(docs)}")

        if not docs:
            return "No encontré documentos relevantes tras intentar incluso una búsqueda general sin filtros."

        system_notice = ""
        if fallback_active and docs:
            system_notice = (
                "[AVISO SISTEMA]: No se encontraron resultados con tus filtros específicos "
                f"(date_from='{date_from}', source='{source_filter}', type='{doc_type}'). "
                "Se realizó una búsqueda general por similitud semántica para encontrar contexto relevante.\n\n"
            )

        return system_notice + "\n\n".join(
            f"[Fuente: {d.metadata.get('source', 'desconocida')} | "
            f"Tipo: {d.metadata.get('doc_type', 'general')}]\n{d.page_content}"
            for d in docs
        )
    except Exception as e:
        logger.error(f"Error en knowledge_base_retriever: {e}")
        return f"{TOOL_ERROR_PREFIX} {str(e)}"
