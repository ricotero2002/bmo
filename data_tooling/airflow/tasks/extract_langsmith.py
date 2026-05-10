from langsmith import Client
import pandas as pd
from datetime import datetime, timedelta, timezone
import json
import os
import argparse
import logging
import sys
import gc

# Asegurar acceso a los providers del proyecto
sys.path.append("/opt/project")
from src.providers.storage.data_lake_provider import DataLakeProvider

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

CHUNK_SIZE = 1000  # Límite de filas en RAM por chunk


def fetch_yesterday_data(
    ds,
    project_name=None,
    start_time_custom=None,
    end_time_custom=None,
):
    """
    Extrae trazas de LangSmith de forma incremental en chunks para evitar OOM.
    ds: YYYY-MM-DD (fecha de ejecución de Airflow)
    """
    if project_name is None:
        project_name = os.getenv("LANGCHAIN_PROJECT", "BMO")

    client = Client()

    # ── Ventana de tiempo ──────────────────────────────────────────────────
    if start_time_custom and str(start_time_custom).lower() != "none":
        logger.info(f"🕒 Usando start_time personalizado: {start_time_custom}")
        start_time = datetime.fromisoformat(
            str(start_time_custom).replace("Z", "+00:00")
        )
    else:
        # Siempre timezone-aware (UTC) para evitar el TypeError de comparación
        start_time = datetime.strptime(ds, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    if end_time_custom and str(end_time_custom).lower() != "none":
        logger.info(f"🕒 Usando end_time personalizado: {end_time_custom}")
        end_time = datetime.fromisoformat(
            str(end_time_custom).replace("Z", "+00:00")
        )
    else:
        end_time = start_time + timedelta(days=1)

    logger.info(
        f"🚀 Extrayendo desde LangSmith | proyecto: {project_name} | "
        f"ventana: {start_time.isoformat()} → {end_time.isoformat()}"
    )

    lake_provider = DataLakeProvider()

    # list_runs devuelve un generador (lazy iterator) — no carga todo en memoria
    runs_iterator = client.list_runs(
        project_name=project_name,
        start_time=start_time,
        end_time=end_time,
        execution_order=1,   # Solo root runs (conversaciones completas)
        # name="LangGraph",    # Solo el agente principal
    )

    chunk_data = []
    chunk_idx = 0
    total_processed = 0

    for run in runs_iterator:
        inputs = run.inputs or {}
        outputs = run.outputs or {}
        error_msg = str(run.error) if run.error else None

        # Latencia: ambos timestamps vienen como aware desde LangSmith, la resta es segura
        latency_ms = None
        if run.end_time and run.start_time:
            latency_ms = (run.end_time - run.start_time).total_seconds() * 1000

        chunk_data.append({
            "run_id": str(run.id),
            "date": ds,
            "start_time": run.start_time.isoformat() if run.start_time else None,
            "status": "error" if error_msg else "success",
            "error_message": error_msg,
            "latency_ms": latency_ms,
            "prompt_tokens": run.prompt_tokens or 0,
            "completion_tokens": run.completion_tokens or 0,
            "total_tokens": (run.prompt_tokens or 0) + (run.completion_tokens or 0),
            "total_cost_usd": run.total_cost or 0.0,
            "inputs_json": json.dumps(inputs, default=str),
            "outputs_json": json.dumps(outputs, default=str),
            "tools_used": json.dumps([]),
        })

        # Control de memoria: volcar chunk cuando supera el límite
        if len(chunk_data) >= CHUNK_SIZE:
            save_chunk(chunk_data, lake_provider, ds, chunk_idx)
            total_processed += len(chunk_data)
            chunk_data.clear()
            chunk_idx += 1

    # Volcar el remanente final
    if chunk_data:
        save_chunk(chunk_data, lake_provider, ds, chunk_idx)
        total_processed += len(chunk_data)

    if total_processed == 0:
        logger.warning(f"⚠️ No se encontraron trazas para la fecha {ds}")
    else:
        logger.info(f"🏁 Extracción finalizada. Total trazas: {total_processed}")


def save_chunk(data: list, provider: DataLakeProvider, ds: str, idx: int):
    """Serializa el chunk a Parquet y lo sube a OCI."""
    df = pd.DataFrame(data)

    if idx == 0:
        logger.info(f"📊 Columnas: {df.columns.tolist()}")
        logger.info(f"📝 Muestra (2 filas):\n{df.head(2).to_string()}")

    provider.write_parquet_chunk(df, "bronze", "langsmith_raw", ds, idx)
    # El provider ya hace del df y gc.collect() en su finally
    logger.info(f"✅ Chunk {idx} guardado.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ds", required=True, help="Fecha YYYY-MM-DD")
    parser.add_argument(
        "--project",
        default=os.getenv("LANGCHAIN_PROJECT", "BMO"),
        help="Nombre del proyecto en LangSmith",
    )
    args = parser.parse_args()

    fetch_yesterday_data(args.ds, args.project)
