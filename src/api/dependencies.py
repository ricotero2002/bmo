from fastapi import Request
from src.providers.vector_store.factory import VectorStoreFactory

def get_vector_db(request: Request):
    return request.app.state.vector_store

# Dependencia para el servicio de Embeddings (OpenAI, etc.)
def get_embeddings():
    # Aquí podrías usar una Factory según el entorno
    return VectorStoreFactory.get_embeddings()
#aca falta tambien el del llm.