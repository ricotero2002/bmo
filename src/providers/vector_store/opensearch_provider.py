import os
import logging
from langchain_community.vectorstores import OpenSearchVectorSearch
from src.providers.vector_store.db_provider import DbProvider

logger = logging.getLogger(__name__)


class OpenSearchProvider(DbProvider):
    """
    Proveedor de vector store usando Amazon OpenSearch Service.
    Autenticación via AWS SigV4 (requiere las variables AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY y AWS_REGION en el entorno, o un IAM Role en ECS).

    Dependencias adicionales necesarias:
      pip install requests-aws4auth opensearch-py
    """

    def __init__(self, endpoint: str, embeddings, index_name: str = None):
        self.endpoint = endpoint
        self.embeddings = embeddings
        self.index_name = index_name or os.getenv("AWS_OPENSEARCH_INDEX", "bmo-documents")

    def getVectorStore(self) -> OpenSearchVectorSearch:
        region = os.getenv("AWS_REGION", "us-east-1")
        aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
        aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")

        http_auth = None
        if aws_access_key and aws_secret_key:
            # Autenticación SigV4 con credenciales explícitas (recomendado en local/CI)
            from requests_aws4auth import AWS4Auth
            http_auth = AWS4Auth(
                aws_access_key,
                aws_secret_key,
                region,
                "es",  # Servicio: "es" para OpenSearch managed, "aoss" para Serverless
            )
            logger.info("OpenSearchProvider: usando autenticación SigV4 con credenciales explícitas")
        else:
            # En ECS/Lambda con IAM Role, boto3 toma las credenciales automáticamente
            import boto3
            credentials = boto3.Session().get_credentials().get_frozen_credentials()
            from requests_aws4auth import AWS4Auth
            http_auth = AWS4Auth(
                credentials.access_key,
                credentials.secret_key,
                region,
                "es",
                session_token=credentials.token,
            )
            logger.info("OpenSearchProvider: usando autenticación SigV4 via IAM Role")

        return OpenSearchVectorSearch(
            index_name=self.index_name,
            embedding_function=self.embeddings,
            opensearch_url=self.endpoint,
            http_auth=http_auth,
            use_ssl=True,
            verify_certs=True,
            ssl_assert_hostname=False,
            ssl_show_warn=False,
        )
