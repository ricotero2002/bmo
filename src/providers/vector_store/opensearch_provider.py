from langchain_community.vectorstores import OpenSearchVectorSearch
from src.providers.vector_store.db_provider import DbProvider

class OpenSearchProvider(DbProvider):
    def __init__(self, endpoint, embeddings):
        self.endpoint = endpoint
        self.embeddings = embeddings

    def getVectorStore(self):
        # Asegúrate de ajustar parámetros como credentials, use_ssl, etc, según tu server
        return OpenSearchVectorSearch(
            index_name="example_collection",
            embedding_function=self.embeddings,
            opensearch_url=self.endpoint,
            use_ssl=True,
            verify_certs=True
        )
