from pyspark.sql import SparkSession
from pyspark.sql.functions import col, lit, when
import argparse

def process_silver(ds):
    spark = SparkSession.builder \
        .appName(f"Telemetry_Silver_{ds}") \
        .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions") \
        .getOrCreate()

    print(f"🚀 Processing Silver for date: {ds}")

    # 1. Read from Bronze
    input_path = f"s3://bronze/langsmith_raw/date={ds}/"
    df_raw = spark.read.parquet(input_path)

    # 2. Transformations
    # Clean JSON, calculate metrics, etc.
    df_silver = df_raw.withColumn("is_expensive", col("cost_usd") > 0.05) \
                      .withColumn("date", lit(ds)) # Ensure date matches partition

    # 3. Idempotent Save to Iceberg Silver
    # replaceWhere ensures we only overwrite the partition for the current 'ds'
    df_silver.write.format("iceberg") \
        .mode("overwrite") \
        .option("replaceWhere", f"date = '{ds}'") \
        .save("lakehouse.silver.agent_runs")

    print(f"✅ Silver processing complete for {ds}")
    spark.stop()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ds", required=True, help="Execution date YYYY-MM-DD")
    args = parser.parse_args()
    
    process_silver(args.ds)
