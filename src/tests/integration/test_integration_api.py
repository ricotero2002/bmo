import pytest
from fastapi.testclient import TestClient
# from testcontainers.chroma import ChromaContainer

from src.api.main import app
# from src.providers.vector_store.factory import VectorStoreFactory

# ==============================================================================
# ESQUEMA PARA TESTS DE INTEGRACION CON CHROMA REAL (Vía Testcontainers)
# ==============================================================================
#
# Para cuando decidas implementar tests reales de base de datos en Python:
# 1. Instala testcontainers: `pip install testcontainers[chroma]`
# 2. Descomenta el fixture de abajo y el uso del test.
#
# ==============================================================================

"""
@pytest.fixture(scope="module")
def chroma_server():
    # Levanta un contenedor Docker efímero con Chroma solo para pruebas
    with ChromaContainer() as chroma:
        server_url = chroma.get_connection_url()
        # Parseamos el host y puerto
        host = server_url.split("://")[1].split(":")[0]
        port = int(server_url.split(":")[2])
        yield host, port

@pytest.fixture
def integration_client(chroma_server):
    host, port = chroma_server
    
    # Sobrescribimos el Factory local para que no use el del .env.local 
    # sino el de testcontainers
    def override_get_provider():
        from src.providers.vector_store.chroma_provider import ChromaProvider
        from src.api.dependencies import get_embeddings
        return ChromaProvider(host=host, port=port, embeddings=get_embeddings())
        
    app.dependency_overrides[get_provider] = override_get_provider
    
    with TestClient(app) as client:
        yield client
        
    app.dependency_overrides = {}

def test_integration_ingest(integration_client):
    # En este test, NO HABRÁ MOCKS de BD, se guardará en el contenedor real
    fake_pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    response = integration_client.post(
        "/api/ingest",
        files={"file": ("integration_test.pdf", fake_pdf_content, "application/pdf")}
    )
    
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    
    # A continuación se podría hacer un similarity_search para comprobar 
    # que la base de datos realmente indexó y guardó los vectores
"""
