import os
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from src.providers.vector_store.chroma_provider import ChromaProvider
from src.providers.vector_store.opensearch_provider import OpenSearchProvider


class VectorStoreFactory:
    @staticmethod
    def get_embeddings():
        return GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")

    @staticmethod
    def get_provider():
        env = os.getenv("APP_ENV", "local")
        embeddings = VectorStoreFactory.get_embeddings()

        if env == "production":
            return OpenSearchProvider(
                endpoint=os.getenv("AWS_OPENSEARCH_URL"),
                embeddings=embeddings,
                index_name=os.getenv("AWS_OPENSEARCH_INDEX", "bmo-documents"),
            )

        # Default: desarrollo local (ChromaDB en Docker)
        return ChromaProvider(
            host=os.getenv("CHROMA_HOST", "localhost"),
            port=int(os.getenv("CHROMA_PORT", 8000)),
            embeddings=embeddings,
            collection_name=os.getenv("COLLECTION_NAME", "example_collection"),
        )