from src.providers.vector_store.db_provider import DbProvider

class ChromaProvider(DbProvider):
    def __init__(self, host, port, embeddings,collection_name):
        self.host = host
        self.port = port
        self.embeddings = embeddings
        self.collection_name=collection_name
        
    def getVectorStore(self):
        import chromadb
        from langchain_chroma import Chroma
        
        client = chromadb.HttpClient(host=self.host, port=self.port)
        return Chroma(
            collection_name=self.collection_name,
            embedding_function=self.embeddings,
            client=client
        )