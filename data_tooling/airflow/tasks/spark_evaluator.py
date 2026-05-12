import os
import sys
import json
import logging
import argparse
import pandas as pd
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, lit

# Asegurar acceso a los providers del proyecto
sys.path.append("/opt/project")
from src.providers.lakehouse.spark_utils import get_iceberg_spark_session

# Configuración de logs para el worker
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from src.evals.eval_utils import NvidiaJudge


# =========================================================================
# EVALUACIÓN EN PYTHON PURO — corre en el worker de Airflow, no en Spark
# =========================================================================
def evaluate_single_run(row: dict) -> dict:
    """Evalúa un run individual. Se llama desde pandas.apply(), no desde un UDF de Spark."""
    try:
        from deepeval.test_case import LLMTestCase
        from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric

        inputs = json.loads(row["inputs_json"]) if row["inputs_json"] else {}
        outputs = json.loads(row["outputs_json"]) if row["outputs_json"] else {}

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
                if "### Fuentes" in content:
                    content = content.split("### Fuentes")[0].strip()
                elif "Fuentes:" in content:
                    content = content.split("Fuentes:")[0].strip()
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

        test_case = LLMTestCase(
            input=user_input, 
            actual_output=ai_output, 
            retrieval_context=retrieval_context
        )
        
        # Ejecutamos métricas (DeepEval internamente maneja el loop si se miden juntas)
        relevancy_metric.measure(test_case)
        faithfulness_metric.measure(test_case)

        return {
            "answer_relevancy": float(relevancy_metric.score),
            "faithfulness": float(faithfulness_metric.score),
            "relevancy_reason": str(relevancy_metric.reason),
            "faithfulness_reason": str(faithfulness_metric.reason)
        }

    except Exception as e:
        import traceback
        logger.error(f"Error evaluando run {row.get('run_id')}: {e}")
        return {
            "answer_relevancy": None,
            "faithfulness": None,
            "relevancy_reason": f"ERROR: {e}",
            "faithfulness_reason": traceback.format_exc()
        }


# =========================================================================
# JOB PRINCIPAL
# =========================================================================
def process_evaluations(ds, sample_fraction=1.0, max_runs=50):
    spark = get_iceberg_spark_session(f"Telemetry_Gold_Eval_{ds}")
    logger.info(f"🚀 Iniciando JOB de evaluación (Spark Connect) para: {ds}")

    df_silver = (
        spark.read.format("iceberg")
        .load("lakehouse.silver.stg_agent_runs")
        .filter(col("date") == lit(ds))
    )
    
    # ── 1. Errores: Spark los escribe directo, no necesitan evaluación ──────────
    df_errors = df_silver.filter(col("is_error") == True)
    error_count = df_errors.count()
    if error_count > 0:
        logger.info(f"🔎 Registrando {error_count} errores.")
        
        spark.sql("""
            CREATE TABLE IF NOT EXISTS lakehouse.gold.agent_errors (
                run_id STRING,
                date STRING,
                error_message STRING,
                ingested_at TIMESTAMP
            ) USING iceberg
        """)
        
        df_errors.select("run_id", "date", "error_message", "ingested_at") \
            .write.format("iceberg").mode("append").save("lakehouse.gold.agent_errors")

    # ── 2. Calidad: collect → evaluar en Python → escribir de vuelta ───────────
    df_success = df_silver.filter(col("is_error") == False)
    success_count = df_success.count()
    if success_count > 0:
        logger.info(f"⚖️ Recolectando muestra para evaluar ({sample_fraction*100:.0f}%, max {max_runs})... ({success_count} disponibles)")
        
        # .toPandas() trae los datos al worker de Airflow (donde sí está deepeval)
        pdf: pd.DataFrame = (
            df_success
            .sample(withReplacement=False, fraction=float(sample_fraction))
            .limit(int(max_runs))
            .select("run_id", "date", "inputs_json", "outputs_json", "ingested_at")
            .toPandas()
        )

        if len(pdf) == 0:
            logger.warning("⚠️ Muestra vacía tras muestreo.")
            spark.stop()
            return

        logger.info(f"📊 Evaluando {len(pdf)} runs con deepeval en el worker local...")

        # Evaluación en Python puro — deepeval está instalado en Airflow, no en Spark
        eval_results = pdf.apply(evaluate_single_run, axis=1, result_type="expand")
        pdf_final = pd.concat([
            pdf[["run_id", "date", "ingested_at"]],
            eval_results
        ], axis=1)

        logger.info(f"✅ Evaluación finalizada. Escribiendo resultados a Iceberg...")
        
        # Spark escribe el resultado de vuelta a Iceberg
        spark.sql("""
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

        # Convertimos de vuelta a Spark DataFrame para escribir en Iceberg
        df_final = spark.createDataFrame(pdf_final)
        df_final.write.format("iceberg").mode("overwrite") \
            .option("replaceWhere", f"date = '{ds}'") \
            .save("lakehouse.gold.agent_evaluations")
        
        logger.info(f"🎉 {len(pdf_final)} evaluaciones escritas en lakehouse.gold.agent_evaluations")
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
