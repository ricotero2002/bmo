import os
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from src.providers.vector_store.chroma_provider import ChromaProvider
from src.providers.vector_store.pinecone_provider import PineconeProvider


class VectorStoreFactory:
    @staticmethod
    def get_embeddings():
        return GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")

    @staticmethod
    def get_provider():
        env = os.getenv("APP_ENV", "local")
        embeddings = VectorStoreFactory.get_embeddings()

        if env == "production":
            # Producción: Pinecone Starter (Always Free)
            return PineconeProvider(
                embeddings=embeddings,
                index_name=os.getenv("PINECONE_INDEX_NAME", "bmo-documents"),
            )

        # Default: desarrollo local (ChromaDB en Docker)
        return ChromaProvider(
            host=os.getenv("CHROMA_HOST", "localhost"),
            port=int(os.getenv("CHROMA_PORT", 8000)),
            embeddings=embeddings,
            collection_name=os.getenv("COLLECTION_NAME", "example_collection"),
        )