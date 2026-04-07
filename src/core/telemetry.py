from opentelemetry import metrics

# Obtenemos el "medidor" global
meter = metrics.get_meter("personal-ai-metrics")

class AppMetrics:
    def __init__(self):
        # 1. Contador: ¿Cuántos documentos procesamos y cómo salieron?
        self.docs_processed = meter.create_counter(
            "bmo.documents.processed.total",
            description="Total de documentos procesados por la pipeline"
        )
        
        # 2. Histograma: ¿Cuánto tarda la extracción de texto? (En segundos)
        self.extraction_duration = meter.create_histogram(
            "bmo.extraction.duration.seconds",
            description="Tiempo dedicado a extraer texto de los archivos"
        )
        
        # 3. Contador: Consumo del LLM (Muy útil para controlar costos)
        self.llm_tokens = meter.create_counter(
            "bmo.llm.tokens.total",
            description="Total de tokens consumidos por el LLM"
        )
        self.llm_tokens_input = meter.create_counter(
            "bmo.llm.tokens.input",
            description="Total de input tokens consumidos por el LLM"
        )
        self.llm_tokens_output = meter.create_counter(
            "bmo.llm.tokens.output",
            description="Total de output tokens consumidos por el LLM"
        )

# Instancia global para importar en otros archivos
metrics_registry = AppMetrics()

# --- Callback Handler para LangChain ---
from langchain_core.callbacks import BaseCallbackHandler

class TelemetryCallbackHandler(BaseCallbackHandler):
    def on_llm_end(self, response, **kwargs):
        try:
            total_tokens = 0
            input_tokens = 0
            output_tokens = 0
            model_name = "unknown"
            
            # Check llm_output directly
            llm_output = getattr(response, "llm_output", {}) or {}
            token_usage = llm_output.get("token_usage", {})
            if token_usage:
                total_tokens = token_usage.get("total_tokens", 0)
            
            if "model_name" in llm_output:
                model_name = llm_output["model_name"]

            # Fallback for structured/streaming chunks
            for generation in response.generations:
                for chunk in generation:
                    message = getattr(chunk, "message", None)
                    if message:
                        # Langchain > 0.2 Standard for usage
                        if hasattr(message, "usage_metadata") and message.usage_metadata:
                            total_tokens = message.usage_metadata.get("total_tokens", 0)
                            input_tokens += message.usage_metadata.get("input_tokens", 0)
                            output_tokens += message.usage_metadata.get("output_tokens", 0)
                        
                        # Fallback to response_metadata
                        elif hasattr(message, "response_metadata"):
                            meta = message.response_metadata
                            if "model_name" in meta and model_name == "unknown":
                                model_name = meta["model_name"]
                            if "token_usage" in meta:
                                if isinstance(meta["token_usage"], dict):
                                    total_tokens = meta["token_usage"].get("total_tokens", 0)
                                    input_tokens += meta["token_usage"].get("prompt_tokens", 0)
                                    output_tokens += meta["token_usage"].get("completion_tokens", 0)
                                else:
                                    total_tokens = getattr(meta["token_usage"], "total_tokens", 0)
                                    input_tokens += getattr(meta["token_usage"], "prompt_tokens", 0)
                                    output_tokens += getattr(meta["token_usage"], "completion_tokens", 0)
            if total_tokens > 0:
                metrics_registry.llm_tokens.add(total_tokens, {"model": model_name})
            if input_tokens > 0:
                metrics_registry.llm_tokens_input.add(input_tokens, {"model": model_name})
            if output_tokens > 0:
                metrics_registry.llm_tokens_output.add(output_tokens, {"model": model_name})
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Error in TelemetryCallbackHandler: {e}")

