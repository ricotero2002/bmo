from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # App
    APP_ENV: str = "local"
    
    # Ingestion Validation
    ALLOWED_EXTENSIONS: list = [".pdf", ".docx", ".txt", ".md", ".json", ".csv"]
    MAX_FILE_SIZE: int = 1000 * 1024 * 1024  # 1gb
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # RabbitMQ / Celery
    CELERY_BROKER_URL: str = "pyamqp://guest@localhost//"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"
    
    # Celery Config
    celery_task_serializer: str = "json"
    celery_result_serializer: str = "json"
    celery_accept_content: list = ["json"]
    celery_timezone: str = "UTC"
    celery_enable_utc: bool = True
    
    worker_prefetch_multiplier: int = 1
    worker_max_tasks_per_child: int = 50
    
    # Infrastructure — Local
    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8000
    COLLECTION_NAME: str = "personal_assistant"
    
    POSTGRES_USER: str = "user"
    POSTGRES_PASSWORD: str = "password"
    POSTGRES_DB: str = "record_manager"
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    
    # AI Services
    OPENAI_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    
    # Monitoring
    LANGSMITH_API_KEY: str = ""
    LANGCHAIN_TRACING_V2: str = "false"
    LANGSMITH_PROJECT: str = "default"
    
    # External APIs
    OPENWEATHERMAP_API_KEY: str = ""

    # MinIO / Object Storage (local)
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "admin"
    MINIO_SECRET_KEY: str = "password"
    MINIO_SECURE: bool = False
    MINIO_BUCKET_NAME: str = "documents"

    # Kafka (Fase 3)
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_RAW_DOCUMENTS_TOPIC: str = "raw-documents"
    KAFKA_DLT_TOPIC: str = "raw-documents-dlt"

    # ── AWS (Fase 4 — Producción) ────────────────────────────────────────────
    # Las credenciales AWS pueden configurarse aquí o via IAM Role en ECS (recomendado)
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"

    # S3 — Reemplaza MinIO en producción
    AWS_S3_BUCKET: str = "bmo-documents"

    # OpenSearch — Reemplaza ChromaDB en producción
    AWS_OPENSEARCH_URL: str = ""
    AWS_OPENSEARCH_INDEX: str = "bmo-documents"

    # DynamoDB — Caché (reemplaza Redis) y Checkpointer (alternativa a RDS)
    AWS_DYNAMODB_TABLE_CACHE: str = "bmo-cache"
    AWS_DYNAMODB_TABLE_CHECKPOINTER: str = "bmo-checkpoints"

settings = Settings()
