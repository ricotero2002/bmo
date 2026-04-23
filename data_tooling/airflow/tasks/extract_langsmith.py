from langsmith import Client
import pandas as pd
from datetime import datetime, timedelta
import json
import os
import argparse

def fetch_yesterday_data(ds, project_name="bmo_production_rag"):
    """
    ds: YYYY-MM-DD (Airflow execution date)
    """
    client = Client()
    start_time = datetime.strptime(ds, "%Y-%m-%d")
    end_time = start_time + timedelta(days=1)

    print(f"🚀 Fetching data for {ds} from LangSmith project: {project_name}")

    # execution_order=1 brings the "Root Span" (the whole conversation)
    runs = list(client.list_runs(
        project_name=project_name,
        start_time=start_time,
        end_time=end_time,
        execution_order=1
    ))

    dataset = []
    for run in runs:
        # Extract full Inputs and Outputs
        inputs = run.inputs or {}
        outputs = run.outputs or {}
        
        # Extract errors if any
        error_msg = str(run.error) if run.error else None
        status = "error" if error_msg else "success"

        # Extract Child Runs to find Tools used
        child_runs = list(client.list_runs(project_name=project_name, id=run.id)) # Correcting to check children of this run
        # Note: LangSmith client.list_runs filter for children is usually done via parent_run_id
        # but the user's snippet used reference_example_id which might be specific to their view.
        # Standard way is filtering by parent_run_id
        child_runs = list(client.list_runs(project_name=project_name, parent_run_id=run.id))
        tools_used = [child.name for child in child_runs if child.run_type == "tool"]

        dataset.append({
            "trace_id": str(run.id),
            "date": ds,
            "status": status,
            "error_message": error_msg,
            "latency_ms": (run.end_time - run.start_time).total_seconds() * 1000 if run.end_time and run.start_time else None,
            "total_tokens": (run.prompt_tokens or 0) + (run.completion_tokens or 0),
            "cost_usd": run.total_cost or 0.0,
            "inputs_json": json.dumps(inputs),
            "outputs_json": json.dumps(outputs),
            "tools_used": json.dumps(tools_used)
        })

    if not dataset:
        print(f"⚠️ No data found for {ds}")
        return

    df = pd.DataFrame(dataset)
    
    # Save raw to MinIO (Bronze)
    # endpoint_url is usually passed via storage_options for s3fs
    endpoint = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
    access_key = os.getenv("MINIO_ACCESS_KEY", "admin")
    secret_key = os.getenv("MINIO_SECRET_KEY", "password")
    
    file_path = f"s3://bronze/langsmith_raw/date={ds}/data.parquet"
    
    storage_options = {
        "key": access_key,
        "secret": secret_key,
        "client_kwargs": {"endpoint_url": endpoint}
    }
    
    df.to_parquet(file_path, storage_options=storage_options, index=False)
    print(f"✅ {len(df)} traces saved to {file_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.get_terminal_size()
    parser.add_argument("--ds", required=True, help="Execution date YYYY-MM-DD")
    parser.add_argument("--project", default="bmo_production_rag", help="LangSmith project name")
    args = parser.parse_args()
    
    fetch_yesterday_data(args.ds, args.project)
