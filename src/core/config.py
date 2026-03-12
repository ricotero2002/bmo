from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env.local",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # App
    APP_ENV: str = "local"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # RabbitMQ / Celery
    RABBITMQ_URL: str = "pyamqp://guest@localhost//"
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
    
    # Infrastructure
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

    # MinIO / Object Storage
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "admin"
    MINIO_SECRET_KEY: str = "password"
    MINIO_SECURE: bool = False
    MINIO_BUCKET_NAME: str = "documents"

    # Kafka (Optional for later phases)
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"

settings = Settings()
