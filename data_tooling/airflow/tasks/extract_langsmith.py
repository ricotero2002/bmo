from langsmith import Client
import pandas as pd
from datetime import datetime, timedelta
import json
import os
import argparse
import logging
import sys

# Asegurar acceso a los providers del proyecto
sys.path.append("/opt/project")
from src.providers.storage.data_lake_provider import DataLakeProvider

# Configuración de Logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

CHUNK_SIZE = 1000  # Límite de filas en RAM por chunk

def fetch_yesterday_data(ds, project_name="bmo_production_rag"):
    """
    Extrae trazas de LangSmith de forma incremental en chunks para evitar OOM.
    ds: YYYY-MM-DD (fecha de ejecución de Airflow)
    """
    client = Client()
    start_time = datetime.strptime(ds, "%Y-%m-%d")
    end_time = start_time + timedelta(days=1)
    
    lake_provider = DataLakeProvider()

    logger.info(f"🚀 Iniciando extracción desde LangSmith. Proyecto: {project_name}, Fecha: {ds}")

    # list_runs devuelve un generador (lazy iterator)
    runs_iterator = client.list_runs(
        project_name=project_name,
        start_time=start_time,
        end_time=end_time,
        execution_order=1 # Solo root runs (conversaciones completas)
    )

    chunk_data = []
    chunk_idx = 0
    total_processed = 0

    for run in runs_iterator:
        inputs = run.inputs or {}
        outputs = run.outputs or {}
        error_msg = str(run.error) if run.error else None
        
        # Extraer herramientas usadas (child runs de tipo 'tool')
        # Nota: Esto puede ser lento si hay miles de runs. 
        # En una fase posterior se podría optimizar trayendo todos los runs y agrupando en Spark.
        try:
            child_runs = list(client.list_runs(project_name=project_name, parent_run_id=run.id))
            tools_used = [child.name for child in child_runs if getattr(child, 'run_type', '') == "tool"]
        except Exception as e:
            logger.warning(f"Error al obtener child runs para {run.id}: {e}")
            tools_used = []

        chunk_data.append({
            "run_id": str(run.id),
            "date": ds,
            "start_time": run.start_time.isoformat() if run.start_time else None,
            "status": "error" if error_msg else "success",
            "error_message": error_msg,
            "latency_ms": (run.end_time - run.start_time).total_seconds() * 1000 if run.end_time and run.start_time else None,
            "prompt_tokens": run.prompt_tokens or 0,
            "completion_tokens": run.completion_tokens or 0,
            "total_tokens": (run.prompt_tokens or 0) + (run.completion_tokens or 0),
            "total_cost_usd": run.total_cost or 0.0,
            "inputs_json": json.dumps(inputs),
            "outputs_json": json.dumps(outputs),
            "tools_used": json.dumps(tools_used)
        })

        # Control de Memoria: Guardar si alcanzamos el tamaño del chunk
        if len(chunk_data) >= CHUNK_SIZE:
            save_chunk(chunk_data, lake_provider, ds, chunk_idx)
            total_processed += len(chunk_data)
            chunk_data.clear()
            chunk_idx += 1

    # Guardar último remanente
    if chunk_data:
        save_chunk(chunk_data, lake_provider, ds, chunk_idx)
        total_processed += len(chunk_data)

    if total_processed == 0:
        logger.warning(f"⚠️ No se encontraron trazas para la fecha {ds}")
    else:
        logger.info(f"🏁 Extracción finalizada. Total trazas procesadas: {total_processed}")

def save_chunk(data, provider, ds, idx):
    """Convierte a DataFrame, loguea info y guarda en el lake."""
    df = pd.DataFrame(data)
    
    # Debugging logs
    if idx == 0:
        logger.info(f"📊 Columnas detectadas: {df.columns.tolist()}")
        logger.info(f"📝 Ejemplo de datos (primeras 2 filas):\n{df.head(2).to_string()}")

    provider.write_parquet_chunk(df, "bronze", "langsmith_raw", ds, idx)
    logger.info(f"✅ Chunk {idx} guardado exitosamente.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ds", required=True, help="Execution date YYYY-MM-DD")
    parser.add_argument("--project", default="bmo_production_rag", help="LangSmith project name")
    args = parser.parse_args()
    
    fetch_yesterday_data(args.ds, args.project)
