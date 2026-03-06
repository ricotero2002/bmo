from langchain_chroma import Chroma
from src.providers.vector_store.db_provider import DbProvider
class ChromaProvider(DbProvider):
    def __init__(self, path, embeddings):
        self.path = path
        self.embeddings = embeddings
    def getVectorStore(self):
        return Chroma(
            collection_name="example_collection",
            embedding_function=self.embeddings,
            persist_directory=self.path  # Usamos el path del constructor en su lugar
        )