import os
import pandas as pd
from langsmith import Client
from datetime import datetime, timezone
from dotenv import load_dotenv


# 1. Configura tus credenciales 
# (Reemplaza con tu API Key real si no está en las variables de entorno)
load_dotenv(override=True)
os.environ.setdefault("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com")
os.environ["LANGCHAIN_API_KEY"] = "lsv2_pt_..." 

# 2. Inicializar cliente
client = Client()
PROJECT_NAME = "BMO"  # El nombre exacto de tu proyecto en LangSmith

# --- FILTRO DE TIEMPO (Basado en tu dataset de Locust) ---
# El test de hoy (07/04/2026) ocurrió aproximadamente entre las 18:15 y 18:25 UTC.
START_TIME = datetime(2026, 4, 7, 18, 15, 0, tzinfo=timezone.utc)
END_TIME = datetime(2026, 4, 7, 18, 30, 0, tzinfo=timezone.utc)

print(f"📡 Conectando con LangSmith...")
print(f"🕒 Buscando runs entre {START_TIME} y {END_TIME} en el proyecto '{PROJECT_NAME}'...")

# 3. Obtener los runs
# is_root=True trae solo la ejecución "padre" (el turno completo del chat)
# Filtramos por start_time >= START_TIME
runs = client.list_runs(
    project_name=PROJECT_NAME,
    is_root=True,
    start_time=START_TIME
)

data = []
for run in runs:
    # Si tenemos un END_TIME, filtramos manualmente (list_runs no tiene end_time directo en algunos filtros)
    if run.start_time > END_TIME:
        continue

    # LangSmith guarda las métricas de tokens y costos
    prompt_tokens = getattr(run, 'prompt_tokens', 0) or 0
    completion_tokens = getattr(run, 'completion_tokens', 0) or 0
    total_tokens = getattr(run, 'total_tokens', 0) or 0
    
    # --- FIX: FORZAR FLOAT PARA EVITAR ERRORES DE SUMA CON DECIMAL ---
    raw_cost = getattr(run, 'total_cost', 0.0)
    total_cost = float(raw_cost) if raw_cost is not None else 0.0
    
    # Extraer latencia
    latency_ms = 0
    if run.end_time and run.start_time:
        latency_ms = (run.end_time - run.start_time).total_seconds() * 1000

    # Extraer metadata (User ID, Thread ID)
    metadata = run.extra.get("metadata", {}) if run.extra else {}
    user_id = metadata.get("user_id", "N/A")
    thread_id = metadata.get("thread_id", "N/A")
    test_type = metadata.get("test_type", "load_test")

    # Extraer tags
    tags = ", ".join(run.tags) if run.tags else ""

    data.append({
        "Run ID": str(run.id),
        "Name": run.name,
        "Start Time": run.start_time,
        "Latency (ms)": round(latency_ms, 2),
        "Status": run.status,
        "User ID": user_id,
        "Thread ID": thread_id,
        "Test Type": test_type,
        "Tags": tags,
        "Prompt Tokens": prompt_tokens,
        "Completion Tokens": completion_tokens,
        "Total Tokens": total_tokens,
        "Total Cost ($)": total_cost,
    })

# 4. Convertir a Pandas y guardar
if not data:
    print("❌ No se encontraron runs en ese rango de tiempo.")
else:
    df = pd.DataFrame(data)
    df = df.sort_values(by="Start Time", ascending=False)
    
    output_filename = "docs/tests/locust_07_04_2026_30users/langsmith_metrics_export.csv"
    df.to_csv(output_filename, index=False)

    print(f"✅ ¡Exportación completada! Se procesaron {len(df)} runs.")
    print(f"💾 Archivo generado: {output_filename}")
    print(f"💸 Costo total registrado en este rango: ${df['Total Cost ($)'].sum():.4f}")
    print(f"⏱️ Latencia promedio: {df['Latency (ms)'].mean():.2f} ms")
