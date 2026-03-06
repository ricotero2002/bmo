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
            # Configuración para AWS OpenSearch
            return OpenSearchProvider(
                endpoint=os.getenv("AWS_OPENSEARCH_URL"),
                embeddings=embeddings
            )
            
        # Configuración por defecto para desarrollo local
        return ChromaProvider(
            path="./data/chroma",
            embeddings=embeddings
        )