import os
from langchain_classic.indexes import SQLRecordManager

class RecordManagerFactory:
    @staticmethod
    def get_manager():
        env = os.getenv("APP_ENV", "local")        
        POSTGRES_USER = os.getenv("POSTGRES_USER", "localhost")
        POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "localhost")
        POSTGRES_DB = os.getenv("POSTGRES_DB", "localhost")
        DB_PORT = os.getenv("DB_PORT", "localhost") 
        db_url=f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}@db:{DB_PORT}/{POSTGRES_DB}"
        collection_name = os.getenv("COLLECTION_NAME", "example_collection")
        record_manager = SQLRecordManager(
            collection_name, db_url=db_url
        )
        # Create the necessary table in the database if it doesn't exist
        record_manager.create_schema()

        return record_manager