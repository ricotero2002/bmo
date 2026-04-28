import os
from langchain_google_genai import GoogleGenerativeAIEmbeddings


class VectorStoreFactory:
    @staticmethod
    def get_embeddings():
        # return GoogleGenerativeAIEmbeddings(
        #     model="models/gemini-embedding-001",
        #     google_api_key=os.getenv("GOOGLE_API_KEY")
        # )
        from langchain_nvidia_ai_endpoints import NVIDIAEmbeddings
        return NVIDIAEmbeddings(
            model="nvidia/nv-embedqa-e5-v5",
            nvidia_api_key=os.getenv("NVIDIA_API_KEY")
        )


    @staticmethod
    def get_provider():
        env = os.getenv("APP_ENV", "local")
        embeddings = VectorStoreFactory.get_embeddings()

        if env == "production":
            from src.providers.vector_store.pinecone_provider import PineconeProvider

            # Producción: Pinecone Starter (Always Free)
            return PineconeProvider(
                embeddings=embeddings,
                index_name=os.getenv("PINECONE_INDEX_NAME", "bmo-documents"),
            )
        else:
            # Default: desarrollo local (ChromaDB en Docker)
            from src.providers.vector_store.chroma_provider import ChromaProvider

            return ChromaProvider(
                host=os.getenv("CHROMA_HOST", "localhost"),
                port=int(os.getenv("CHROMA_PORT", 8000)),
                embeddings=embeddings,
                collection_name=os.getenv("COLLECTION_NAME", "example_collection"),
            )