from src.core.config import settings
from langchain_classic.indexes import SQLRecordManager

class RecordManagerFactory:
    @staticmethod
    def get_manager():
        db_url = f"postgresql+psycopg2://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.POSTGRES_DB}"
        
        record_manager = SQLRecordManager(
            settings.COLLECTION_NAME, 
            db_url=db_url
        )
        # Create the necessary table in the database if it doesn't exist
        record_manager.create_schema()

        return record_manager