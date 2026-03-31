import logging
from datetime import date
from typing import Optional

from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

logger = logging.getLogger(__name__)

# Referencia al vector store — se setea al inicio de la app via ToolRegistry.set_vector_store()
_vector_store = None

# Prefijo que identifica respuestas de error de la tool (para detección en el grafo)
TOOL_ERROR_PREFIX = "ERROR_TOOL:"


def build_metadata_filter(
    date_from: Optional[str] = None,
    source_filter: Optional[str] = None,
    user_id: Optional[str] = None,
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

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


@tool
def knowledge_base_retriever(
    query: str,
    date_from: str = "",
    source_filter: str = "",
    config: RunnableConfig = None,
) -> str:
    """
    Busca y recupera información relevante de la base de conocimientos personal del usuario.

    Usá esta herramienta para CUALQUIER pregunta que requiera acceder a documentos,
    notas, reuniones, CVs u otra información personal almacenada.

    Parámetros:
    - query: El texto o pregunta a buscar (requerido, NO puede estar vacío).
             Ejemplo: "notas de la reunión de hoy", "contenido del CV", "contratos de trabajo".
    - date_from: Fecha mínima de los documentos en formato ISO YYYY-MM-DD (opcional).
                 Úsalo cuando el usuario mencione una fecha o período de tiempo.
                 Ejemplo: si el usuario dice "hoy" y hoy es 2026-03-19, pasá "2026-03-19".
                 Si dice "este mes", pasá el primer día del mes: "2026-03-01".
    - source_filter: Nombre exacto del archivo a filtrar (opcional).
                     Ejemplo: "notas_reunion.pdf", "cv.docx".
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
    )

    if _vector_store is None:
        logger.error("knowledge_base_retriever: vector_store no inicializado.")
        return f"{TOOL_ERROR_PREFIX} la base de conocimientos no está disponible."

    try:
        docs = _vector_store.similarity_search(
            query,
            k=3,
            filter=metadata_filter,
        )
        logger.info(
            f"knowledge_base_retriever: filtro={metadata_filter}, "
            f"docs encontrados={len(docs)}"
        )

        if not docs:
            return "No encontré documentos relevantes con esos criterios de búsqueda."

        return "\n\n".join(
            f"[Fuente: {d.metadata.get('source', 'desconocida')} | "
            f"Fecha: {d.metadata.get('created_at', 'N/A')}]\n{d.page_content}"
            for d in docs
        )
    except Exception as e:
        logger.error(f"Error en knowledge_base_retriever: {e}")
        return f"{TOOL_ERROR_PREFIX} {str(e)}"
