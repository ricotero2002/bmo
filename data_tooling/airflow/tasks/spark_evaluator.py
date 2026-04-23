from pyspark.sql import SparkSession
from pyspark.sql.functions import col, lit, udf
from pyspark.sql.types import StringType, StructType, StructField, FloatType
import argparse

# Placeholder for LLM Evaluator UDF
def evaluate_llm_quality_mock(inputs_json, outputs_json):
    # This is where Ragas or a custom LLM call would happen
    # return "{\"relevancy\": 0.9, \"faithfulness\": 0.8}"
    return "good" # Simple mock

eval_udf = udf(evaluate_llm_quality_mock, StringType())

def process_evaluations(ds):
    spark = SparkSession.builder \
        .appName(f"Telemetry_Gold_Eval_{ds}") \
        .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions") \
        .getOrCreate()

    # CRITICAL: Set checkpoint directory in S3/MinIO
    spark.sparkContext.setCheckpointDir("s3://warehouse/checkpoints/")

    print(f"🚀 Processing Gold (Evaluations & Forensics) for date: {ds}")

    # Load Silver data for the day
    df_silver = spark.read.format("iceberg").load("lakehouse.silver.agent_runs").filter(col("date") == lit(ds))

    # =======================================================
    # BRANCH A: Error Forensics (100% of failures)
    # =======================================================
    df_errors = df_silver.filter(col("status") == "error")
    
    if df_errors.count() > 0:
        print(f"🔎 Analyzing {df_errors.count()} errors...")
        # Optional: Add error categorization logic here
        df_errors.write.format("iceberg").mode("append").save("lakehouse.gold.agent_errors")
    else:
        print("✅ No errors found to analyze.")

    # =======================================================
    # BRANCH B: Quality Evaluation (10% random sample)
    # =======================================================
    df_success = df_silver.filter(col("status") == "success")

    if df_success.count() > 0:
        print(f"⚖️ Evaluating quality for a sample of successful runs...")
        
        # 1. Sampling and Initial Checkpoint
        # Prevents re-sampling if the job fails later
        df_sample = df_success.sample(fraction=0.1, seed=42)
        df_sample = df_sample.checkpoint()

        # 2. Apply Evaluation UDF (This calls the LLM)
        df_evaluated = df_sample.withColumn("evaluations", eval_udf(col("inputs_json"), col("outputs_json")))

        # 3. Post-Evaluation Checkpoint
        # CRITICAL: Save results of expensive LLM calls before writing to final table
        df_evaluated = df_evaluated.checkpoint()

        # 4. Idempotent Save to Iceberg Gold
        df_evaluated.write.format("iceberg") \
            .mode("overwrite") \
            .option("replaceWhere", f"date = '{ds}'") \
            .save("lakehouse.gold.agent_evaluations")
        
        print(f"✅ Quality evaluation complete for {ds}")
    else:
        print("⚠️ No successful runs found to evaluate.")

    spark.stop()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.get_terminal_size()
    parser.add_argument("--ds", required=True, help="Execution date YYYY-MM-DD")
    args = parser.parse_args()
    
    process_evaluations(args.ds)
