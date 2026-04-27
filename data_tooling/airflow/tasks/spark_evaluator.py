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

# =========================================================================
# FACTORY LITE (Embebida para evitar dependencias externas en los workers)
# =========================================================================
class WorkerLLMFactory:
    """
    Versión ligera de la fábrica de modelos, diseñada para correr en workers de Spark.
    Solo soporta OpenRouter y Ollama (los modelos configurados actualmente).
    """
    @staticmethod
    def create_judge():
        # FORZADO: Uso de Ollama con llama_1b_gpu como pidió el usuario
        from langchain_ollama import ChatOllama
        model_name = "llama_1b_gpu"
        base_url = "http://host.docker.internal:11434"
        
        logger.info(f"🤖 Inicializando Juez Ollama: {model_name} en {base_url}")
        
        return ChatOllama(
            model=model_name,
            base_url=base_url,
            temperature=0,
            num_ctx=4096 # Aumentamos contexto para evaluación si es posible
        )

# =========================================================================
# EL JUEZ DE DEEPEVAL
# =========================================================================
from deepeval.models.base_model import DeepEvalBaseLLM

class GeminiJudge(DeepEvalBaseLLM):
    """
    Wrapper de DeepEval que utiliza la fábrica interna del worker.
    """
    def __init__(self, model_name: str = "Judge-Worker"):
        self.model_name = model_name
        self.model = WorkerLLMFactory.create_judge()
        
    def _clean_json(self, text: str) -> str:
        text = text.strip()
        if text.startswith("```json"): text = text[7:]
        elif text.startswith("```"): text = text[3:]
        if text.endswith("```"): text = text[:-3]
        return text.strip()

    def load_model(self):
        return self.model

    def generate(self, prompt: str, schema=None, *args, **kwargs):
        res = self.model.invoke(prompt)
        return self._clean_json(res.content)

    async def a_generate(self, prompt: str, schema=None, *args, **kwargs):
        res = await self.model.ainvoke(prompt)
        return self._clean_json(res.content)

    def get_model_name(self):
        return self.model_name

# =========================================================================
# LA FUNCIÓN UDF: Esto corre en los workers de Spark
# =========================================================================
def evaluate_llm_quality_deepeval(inputs_json_str, outputs_json_str):
    # =========================================================================
    # MOCK (Temporalmente activo)
    # =========================================================================
    try:
        is_approved = len(inputs_json_str or "") % 2 == 0
        if is_approved:
            return json.dumps({
                "answer_relevancy_score": 0.95,
                "faithfulness_score": 0.98,
                "relevancy_reason": "✅ [MOCK] La respuesta es relevante.",
                "faithfulness_reason": "✅ [MOCK] No se detectaron contradicciones."
            })
        else:
            return json.dumps({
                "answer_relevancy_score": 0.40,
                "faithfulness_score": 0.35,
                "relevancy_reason": "❌ [MOCK] La respuesta no aborda la consulta.",
                "faithfulness_reason": "❌ [MOCK] Se detectaron alucinaciones."
            })
    except Exception as e:
        return json.dumps({"error": f"Mock error: {str(e)}"})

    # =========================================================================
    # ORIGINAL (Comentado)
    # =========================================================================
    """
    try:
        from deepeval.test_case import LLMTestCase
        from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric
        
        inputs = json.loads(inputs_json_str) if inputs_json_str else {}
        outputs = json.loads(outputs_json_str) if outputs_json_str else {}

        # 1. Extraer Input
        user_input = "Consulta desconocida"
        if "messages" in inputs and len(inputs["messages"]) > 0:
            msg = inputs["messages"][0]
            user_input = msg[1] if isinstance(msg, list) and len(msg) > 1 else str(msg)

        # 2. Extraer Output y Contexto
        out_messages = outputs.get("messages", [])
        ai_output = ""
        retrieval_context = []

        for msg in out_messages:
            msg_type = msg.get("type", "")
            content = str(msg.get("content", "")).strip()

            if msg_type == "ai" and not content.startswith("[Pensamiento"):
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

        # 3. Evaluar
        judge = GeminiJudge() 
        relevancy_metric = AnswerRelevancyMetric(threshold=0.7, model=judge)
        faithfulness_metric = FaithfulnessMetric(threshold=0.7, model=judge) 

        test_case = LLMTestCase(input=user_input, actual_output=ai_output, retrieval_context=retrieval_context)
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
        return json.dumps({"error": str(e), "traceback": traceback.format_exc()})
    """

eval_udf = udf(evaluate_llm_quality_deepeval, StringType())

# =========================================================================
# JOB PRINCIPAL
# =========================================================================
def process_evaluations(ds):
    spark = get_iceberg_spark_session(f"Telemetry_Gold_Eval_{ds}")

    spark.sparkContext.setCheckpointDir("s3a://warehouse/checkpoints/")

    logger.info(f"🚀 Iniciando JOB de evaluación (Self-Contained) para: {ds}")

    df_silver = spark.read.format("iceberg").load("lakehouse.silver.agent_runs").filter(col("date") == lit(ds))
    
    # Análisis de Errores
    df_errors = df_silver.filter(col("is_error") == True)
    if df_errors.count() > 0:
        logger.info(f"🔎 Registrando {df_errors.count()} errores.")
        df_errors.write.format("iceberg").mode("append").save("lakehouse.gold.agent_errors")

    # Calidad (Modo Test)
    df_success = df_silver.filter(col("is_error") == False)
    if df_success.count() > 0:
        logger.info(f"⚖️ Evaluando 2 registros de éxito (Modo MOCK)...")
        # df_sample = df_success.sample(withReplacement=False, fraction=0.1).limit(50).checkpoint()
        df_sample = df_success.limit(2).checkpoint()

        df_evaluated = df_sample.withColumn("eval_json", eval_udf(col("inputs_json"), col("outputs_json")))

        df_final = df_evaluated \
            .withColumn("answer_relevancy", get_json_object(col("eval_json"), "$.answer_relevancy_score").cast("double")) \
            .withColumn("faithfulness", get_json_object(col("eval_json"), "$.faithfulness_score").cast("double")) \
            .withColumn("relevancy_reason", get_json_object(col("eval_json"), "$.relevancy_reason")) \
            .withColumn("faithfulness_reason", get_json_object(col("eval_json"), "$.faithfulness_reason")) \
            .drop("eval_json", "inputs_json", "outputs_json")

        df_final = df_final.checkpoint()
        df_final.write.format("iceberg").mode("overwrite").option("replaceWhere", f"date = '{ds}'").save("lakehouse.gold.agent_evaluations")
        
        logger.info(f"✅ Evaluación finalizada.")
    else:
        logger.warning(f"⚠️ Sin datos para evaluar.")

    spark.stop()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ds", required=True, help="Execution date YYYY-MM-DD")
    args = parser.parse_args()
    process_evaluations(args.ds)
