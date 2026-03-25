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

# Instancia global para importar en otros archivos
metrics_registry = AppMetrics()

# --- Callback Handler para LangChain ---
from langchain_core.callbacks import BaseCallbackHandler

class TelemetryCallbackHandler(BaseCallbackHandler):
    def on_llm_end(self, response, **kwargs):
        try:
            for generation in response.generations:
                for chunk in generation:
                    # Intentar extraer uso de tokens de metadatos (formato LangChain estándar)
                    usage = getattr(chunk, 'generation_info', {}).get('token_usage', {})
                    if not usage:
                        # Algunos modelos lo ponen en response_metadata
                        usage = response.llm_output.get('token_usage', {})
                    
                    if usage:
                        total_tokens = usage.get('total_tokens', 0)
                        if total_tokens > 0:
                            metrics_registry.llm_tokens.add(total_tokens, {
                                "model": response.llm_output.get('model_name', 'unknown')
                            })
        except Exception:
            pass # No queremos que la telemetría rompa la ejecución
