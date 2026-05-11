import os
import sys
import json
import logging
import argparse
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, lit, udf, get_json_object
from pyspark.sql.types import StringType

# Asegurar acceso a los providers del proyecto
sys.path.append("/opt/project")
from src.providers.lakehouse.spark_utils import get_iceberg_spark_session

# Configuración de logs para el worker
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from src.evals.eval_utils import NvidiaJudge

# =========================================================================
# LA FUNCIÓN UDF: Esto corre en los workers de Spark
# =========================================================================
def evaluate_llm_quality_deepeval(inputs_json_str, outputs_json_str):
    try:
        from deepeval.test_case import LLMTestCase
        from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric
        
        inputs = json.loads(inputs_json_str) if inputs_json_str else {}
        outputs = json.loads(outputs_json_str) if outputs_json_str else {}

        # 1. Extraer Input
        user_input = "Consulta desconocida"
        if "messages" in inputs and len(inputs["messages"]) > 0:
            msg = inputs["messages"][0]
            # Formato esperado: ["user", "texto"] o un objeto mensaje de LangChain
            if isinstance(msg, list) and len(msg) > 1:
                user_input = msg[1]
            elif isinstance(msg, dict) and "content" in msg:
                user_input = msg["content"]
            else:
                user_input = str(msg)

        # 2. Extraer Output y Contexto
        out_messages = outputs.get("messages", [])
        ai_output = ""
        retrieval_context = []

        for msg in out_messages:
            msg_type = msg.get("type", "")
            content = str(msg.get("content", "")).strip()

            if msg_type == "ai" and not content.startswith("[Pensamiento"):
                # Limpiar bloques de fuentes para no sesgar la relevancia
                if "### Fuentes" in content: content = content.split("### Fuentes")[0].strip()
                elif "Fuentes:" in content: content = content.split("Fuentes:")[0].strip()
                ai_output = content
            
            elif msg_type == "tool" and msg.get("name") in ["knowledge_base_retriever", "web_search"]:
                if content and "ERROR" not in content and "No encontré" not in content:
                    retrieval_context.append(content)

        if not retrieval_context:
            retrieval_context = ["No se utilizó contexto de recuperación en este turno."]
        if not ai_output:
            ai_output = "El agente no generó respuesta."

        # 3. Evaluar usando el Juez centralizado de Nvidia NIM
        judge = NvidiaJudge() 
        relevancy_metric = AnswerRelevancyMetric(threshold=0.7, model=judge)
        faithfulness_metric = FaithfulnessMetric(threshold=0.7, model=judge) 

        test_case = LLMTestCase(input=user_input, actual_output=ai_output, retrieval_context=retrieval_context)
        
        # Ejecutamos métricas (DeepEval internamente maneja el loop si se miden juntas)
        relevancy_metric.measure(test_case)
        faithfulness_metric.measure(test_case)

        return json.dumps({
            "answer_relevancy_score": relevancy_metric.score,
            "faithfulness_score": faithfulness_metric.score,
            "relevancy_reason": relevancy_metric.reason,
            "faithfulness_reason": faithfulness_metric.reason
        })

    except Exception as e:
        import traceback
        logger.error(f"Error en UDF de evaluación: {e}")
        return json.dumps({"error": str(e), "traceback": traceback.format_exc()})

eval_udf = udf(evaluate_llm_quality_deepeval, StringType())

# =========================================================================
# JOB PRINCIPAL
# =========================================================================
def process_evaluations(ds, sample_fraction=1.0, max_runs=50):
    spark = get_iceberg_spark_session(f"Telemetry_Gold_Eval_{ds}")
    logger.info(f"🚀 Iniciando JOB de evaluación (Spark Connect) para: {ds}")

    df_silver = spark.read.format("iceberg").load("lakehouse.silver.stg_agent_runs").filter(col("date") == lit(ds))
    
    # Análisis de Errores
    df_errors = df_silver.filter(col("is_error") == True)
    if df_errors.count() > 0:
        logger.info(f"🔎 Registrando {df_errors.count()} errores.")
        
        spark.sql(f"""
            CREATE TABLE IF NOT EXISTS lakehouse.gold.agent_errors (
                run_id STRING,
                date STRING,
                error_message STRING,
                ingested_at TIMESTAMP
            ) USING iceberg
        """)
        
        df_errors.select("run_id", "date", "error_message", "ingested_at") \
            .write.format("iceberg").mode("append").save("lakehouse.gold.agent_errors")

    # Calidad (Modo Test)
    df_success = df_silver.filter(col("is_error") == False)
    if df_success.count() > 0:
        logger.info(f"⚖️ Evaluando registros de éxito (Muestreo: {sample_fraction*100}%, Límite: {max_runs})...")
        df_sample = df_success.sample(withReplacement=False, fraction=float(sample_fraction)).limit(int(max_runs))

        df_evaluated = df_sample.withColumn("eval_json", eval_udf(col("inputs_json"), col("outputs_json")))

        df_final = df_evaluated \
            .withColumn("answer_relevancy", get_json_object(col("eval_json"), "$.answer_relevancy_score").cast("double")) \
            .withColumn("faithfulness", get_json_object(col("eval_json"), "$.faithfulness_score").cast("double")) \
            .withColumn("relevancy_reason", get_json_object(col("eval_json"), "$.relevancy_reason")) \
            .withColumn("faithfulness_reason", get_json_object(col("eval_json"), "$.faithfulness_reason")) \
            .select(
                "run_id", 
                "date", 
                "answer_relevancy", 
                "faithfulness", 
                "relevancy_reason", 
                "faithfulness_reason", 
                "ingested_at"
            )

        # df_final = df_final.checkpoint()
        
        spark.sql(f"""
            CREATE TABLE IF NOT EXISTS lakehouse.gold.agent_evaluations (
                run_id STRING,
                date STRING,
                answer_relevancy DOUBLE,
                faithfulness DOUBLE,
                relevancy_reason STRING,
                faithfulness_reason STRING,
                ingested_at TIMESTAMP
            ) USING iceberg
            PARTITIONED BY (date)
        """)

        df_final.write.format("iceberg").mode("overwrite") \
            .option("replaceWhere", f"date = '{ds}'") \
            .save("lakehouse.gold.agent_evaluations")
        
        logger.info(f"✅ Evaluación finalizada.")
    else:
        logger.warning(f"⚠️ Sin datos para evaluar.")

    spark.stop()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ds", required=True, help="Execution date YYYY-MM-DD")
    parser.add_argument("--sample-fraction", type=float, default=1.0, help="Fraction of runs to evaluate")
    parser.add_argument("--max-runs", type=int, default=50, help="Maximum number of runs to evaluate")
    args = parser.parse_args()
    
    try:
        process_evaluations(args.ds, args.sample_fraction, args.max_runs)
        logger.info("🚀 Script finished successfully.")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Critical error in process_evaluations: {e}", exc_info=True)
        sys.exit(1)
