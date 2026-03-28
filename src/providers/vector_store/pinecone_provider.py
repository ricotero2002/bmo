import os
import logging
from langchain_pinecone import PineconeVectorStore
from src.providers.vector_store.db_provider import DbProvider

logger = logging.getLogger(__name__)


class PineconeProvider(DbProvider):
    """
    Proveedor de vector store usando Pinecone (Plan Starter).

    Dependencias:
      pip install langchain-pinecone pinecone-client

    Variables de entorno requeridas:
      PINECONE_API_KEY      — API key de Pinecone
      PINECONE_INDEX_NAME   — Nombre del índice (debe existir previamente en la consola de Pinecone)
    """

    def __init__(self, embeddings, index_name: str):
        self.embeddings = embeddings
        self.index_name = index_name
        logger.info(f"PineconeProvider iniciado con índice: '{self.index_name}'")

    def getVectorStore(self) -> PineconeVectorStore:
        api_key = os.getenv("PINECONE_API_KEY")
        if not api_key:
            raise ValueError("PINECONE_API_KEY no está configurada en el entorno.")

        logger.info(f"Conectando a Pinecone — índice: '{self.index_name}'")
        return PineconeVectorStore(
            index_name=self.index_name,
            embedding=self.embeddings,
            pinecone_api_key=api_key,
        )
