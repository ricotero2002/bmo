import logging
import uuid
from typing import List, Optional
from deepeval.models.base_model import DeepEvalBaseLLM
from src.core.llm import LLMFactory
from src.providers.vector_store.factory import VectorStoreFactory
from src.providers.record_manager.factory import RecordManagerFactory
from src.providers.database.status_provider import StatusProvider

logger = logging.getLogger(__name__)

class GeminiJudge(DeepEvalBaseLLM):
    """
    Custom DeepEval LLM wrapper using the project's LLMFactory (Gemini-based).
    Ensures evaluation runs with the same models as the production system.
    """
    def __init__(self, model_name: str = "Gemini-2.5-Flash"):
        self.model_name = model_name
        # Forzamos temperature=0 para evitar que el juez alucine formatos raros
        self.model = LLMFactory.create().with_config({"temperature": 0.0})
        
    def _clean_json(self, text: str) -> str:
        """Limpia los bloques de markdown que a veces Gemini añade al JSON"""
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return text.strip()

    def load_model(self):
        return self.model

    def generate(self, prompt: str) -> str:
        res = self.model.invoke(prompt)
        return self._clean_json(res.content)

    async def a_generate(self, prompt: str) -> str:
        res = await self.model.ainvoke(prompt)
        return self._clean_json(res.content)

    def get_model_name(self):
        return self.model_name

class EvalCleanup:
    """Utilities to wipe test data from Pinecone, SQL Record Manager, and Postgres."""
    
    @staticmethod
    def wipe_user_documents(doc_ids: List[str]):
        """
        Removes all traces of the specific documents from the system.
        """
        vector_db = VectorStoreFactory.get_provider().getVectorStore()
        record_manager = RecordManagerFactory.get_manager()
        # status_provider = StatusProvider() # Not used for now

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
        prompt_version="rag_v1"
    )
    
    messages = result.get("messages", [])
    
    # 1. Extraer la respuesta final ignorando pensamientos
    actual_output = ""
    for msg in reversed(messages):
        if hasattr(msg, "content") and msg.type == "ai":
            content_str = str(msg.content).strip()
            if content_str and not content_str.startswith("[Pensamiento"):
                actual_output = content_str
                break
                
    if not actual_output:
        actual_output = "Error: El agente no generó una respuesta válida."
            
    # 2. Extraer TODOS los documentos válidos de TODAS las llamadas a la tool
    retrieval_context = []
    for msg in messages:
        if getattr(msg, "type", "") == "tool" and getattr(msg, "name", "") == "knowledge_base_retriever":
            content_str = str(msg.content)
            # Ignoramos si la tool devolvió un error o si no encontró nada en esa iteración específica
            if "ERROR_TOOL" not in content_str and "No encontré" not in content_str:
                # Separamos y agregamos a la lista maestra sin duplicados
                chunks = [c.strip() for c in content_str.split("\n\n") if c.strip()]
                for c in chunks:
                    if c not in retrieval_context:
                        retrieval_context.append(c)
                
    return actual_output, retrieval_context
