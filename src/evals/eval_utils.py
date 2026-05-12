import logging
import re
import uuid
from typing import List, Optional, Any, Type
from deepeval.models.base_model import DeepEvalBaseLLM
from src.core.llm import LLMFactory
from src.core.llm import LLMFactory
from dotenv import load_dotenv
import os

# --- NUEVO: Importar Tenacity ---
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)
load_dotenv(override=True)

class NvidiaJudge(DeepEvalBaseLLM):
    """
    Custom DeepEval LLM wrapper using the project's LLMFactory (Nvidia NIM-based).
    Ensures evaluation runs with the same models as the production system.
    """
    def __init__(self, model_name: str = "Nvidia-Judge-Model"):
        self.model_name = model_name
        # Forzamos temperature=0 para evitar que el juez alucine formatos raros
        self.model = LLMFactory.create_judge().with_config({"temperature": 0.0})
        
    def _clean_json(self, text: str) -> str:
        """
        Extrae de forma robusta solo el bloque JSON (objeto o array), 
        ignorando cualquier charla adicional (babbling) del modelo.
        """
        # Eliminar bloques de thinking de modelos como Qwen3
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        text = text.strip()
        
        # Busca todo lo que esté entre el primer { o [ y el último } o ]
        match = re.search(r'(\{.*\}|\[.*\])', text, re.DOTALL)
        
        if match:
            clean_text = match.group(1)
            # Limpiamos posibles comillas triples sueltas adentro del match si las hubo
            clean_text = clean_text.replace("```json", "").replace("```", "")
            return clean_text.strip()
            
        return text

    def load_model(self):
        return self.model

    # ELIMINAMOS los @retry de aquí
    def generate(self, prompt: str, schema: Optional[Type] = None, *args, **kwargs) -> Any:
        res = self.model.invoke(prompt)
        cleaned_content = self._clean_json(res.content)
        
        if schema:
            try:
                # Si DeepEval pasa un esquema, validamos el JSON manualmente
                return schema.model_validate_json(cleaned_content)
            except Exception:
                return cleaned_content
        
        return cleaned_content

    # ELIMINAMOS los @retry de aquí también
    async def a_generate(self, prompt: str, schema: Optional[Type] = None, *args, **kwargs) -> Any:
        res = await self.model.ainvoke(prompt)
        cleaned_content = self._clean_json(res.content)
        
        if schema:
            try:
                # Si DeepEval pasa un esquema, validamos el JSON manualmente
                return schema.model_validate_json(cleaned_content)
            except Exception:
                return cleaned_content
                
        return cleaned_content

    def get_model_name(self):
        return self.model_name

class EvalCleanup:
    """Utilities to wipe test data from Pinecone, SQL Record Manager, and Postgres."""
    
    @staticmethod
    def wipe_user_documents(doc_ids: List[str]):
        """
        Removes all traces of the specific documents from the system.
        """
        from src.providers.vector_store.factory import VectorStoreFactory
        from src.providers.record_manager.factory import RecordManagerFactory
        # from src.providers.database.status_provider import StatusProvider

        vector_db = VectorStoreFactory.get_provider().getVectorStore()
        record_manager = RecordManagerFactory.get_manager()

        for doc_id in doc_ids:
            try:
                keys = record_manager.list_keys(group_ids=[doc_id])
                if keys:
                    logger.info(f"[EVAL CLEANUP] Deleting {len(keys)} chunks for doc_id: {doc_id}")
                    vector_db.delete(ids=keys)
                    record_manager.delete_keys(keys)
                logger.info(f"[EVAL CLEANUP] Successfully wiped doc_id: {doc_id}")
            except Exception as e:
                logger.error(f"[EVAL CLEANUP] Failed to wipe doc_id {doc_id}: {e}")

# --- NUEVO: Reintentar el flujo RAG completo si hay error de servidor ---
@retry(
    stop=stop_after_attempt(3), 
    wait=wait_exponential(multiplier=3, min=4, max=20),
    reraise=True
)
async def ask_my_rag(agent_service, query: str, user_id: str = "cosmefulanitotest") -> tuple[str, list[str]]:
    """
    Bridge function to call the actual RAG agent and extract answer + context.
    """
    thread_id = f"eval_{uuid.uuid4()}"
    user_info = {"user_id": user_id, "name": "Cosme Fulanito Test"}
    
    result = await agent_service.chat(
        message=query,
        thread_id=thread_id,
        user_info=user_info,
        prompt_version=os.getenv("PROMPT_VERSION"),
    )
    
    messages = result.get("messages", [])
    
    # 1. Extraer la respuesta final ignorando pensamientos
    actual_output = ""
    for msg in reversed(messages):
        if hasattr(msg, "content") and msg.type == "ai":
            content_str = str(msg.content).strip()
            if content_str and not content_str.startswith("[Pensamiento"):
                
                # --- MAGIA PARA DEEPEVAL ---
                # DeepEval castiga la "Relevancia" si incluimos el bloque de fuentes
                # o links que BMO genera automáticamente. Los removemos solo para el test.
                if "### Fuentes" in content_str:
                    content_str = content_str.split("### Fuentes")[0].strip()
                elif "**Fuentes**" in content_str:
                    content_str = content_str.split("**Fuentes**")[0].strip()
                elif "Fuentes:" in content_str:
                    content_str = content_str.split("Fuentes:")[0].strip()
                
                actual_output = content_str
                break
                
    if not actual_output:
        actual_output = "Error: El agente no generó una respuesta válida."
            
    # 2. Extraer TODOS los documentos válidos de TODAS las llamadas a tools de búsqueda
    retrieval_context = []
    for msg in messages:
        # AHORA TAMBIÉN CAPTURAMOS WEB SEARCH
        if getattr(msg, "type", "") == "tool" and getattr(msg, "name", "") in ["knowledge_base_retriever", "web_search"]:
            content_str = str(msg.content).strip()
            
            # Ignoramos si la tool devolvió un error o si no encontró nada
            if content_str and "ERROR" not in content_str and "No encontré" not in content_str:
                
                # LA MAGIA: Ya NO hacemos split("\n\n"). Guardamos el bloque de texto
                # entero exactamente como lo vio el LLM. Así no rompemos la relación
                # entre el [Contexto Global] y el contenido del chunk.
                if content_str not in retrieval_context:
                    retrieval_context.append(content_str)
                    
    if not retrieval_context:
        # Para evitar que DeepEval crashee si la query era puramente conversacional
        retrieval_context = ["No se utilizó contexto de recuperación en este turno."]
                
    return actual_output, retrieval_context
