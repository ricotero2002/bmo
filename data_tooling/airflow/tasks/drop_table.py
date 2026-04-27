import sys
# Aseguramos que pueda importar tu provider
sys.path.append('/opt/project') 
from src.providers.lakehouse.spark_utils import get_iceberg_spark_session

if __name__ == "__main__":
    print("Conectando al Lakehouse...")
    spark = get_iceberg_spark_session('Drop_Table_Job')
    
    # El comando mágico
    spark.sql("DROP TABLE IF EXISTS lakehouse.bronze.raw_llm_traces")
    
    print("✅ TABLA FANTASMA BORRADA CON EXITO!")
    spark.stop()