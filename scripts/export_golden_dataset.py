import os
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.providers.database.models import ChatFeedback, Message
from src.providers.database.core import get_database_url_and_args

def export_golden_dataset(output_path="evals/golden_dataset_v3.json"):
    # Conectar a la base de datos
    db_url, connect_args = get_database_url_and_args()
    engine = create_engine(db_url, **connect_args)
    Session = sessionmaker(bind=engine)
    session = Session()

    print("Extrayendo correcciones (score = -1 con user_correction) y aciertos (score = 1)...")
    
    # Obtener ejemplos positivos
    positive_feedbacks = session.query(ChatFeedback).filter(ChatFeedback.score == 1).all()
    # Obtener correcciones valiosas
    corrections = session.query(ChatFeedback).filter(ChatFeedback.score == -1, ChatFeedback.user_correction.isnot(None)).all()
    
    dataset = []

    for item in positive_feedbacks:
        dataset.append({
            "input": item.user_prompt or "N/A",
            "actual_output": item.ai_response or "N/A",
            "expected_output": item.ai_response or "N/A", # Was correct
            "feedback_type": "positive"
        })
        
    for item in corrections:
        dataset.append({
            "input": item.user_prompt or "N/A",
            "actual_output": item.ai_response or "N/A",
            "expected_output": f"(Corregido) {item.user_correction}",
            "feedback_type": "correction"
        })
    
    session.close()
    
    # Fusionar con el existente si existe
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    existing_data = []
    
    old_dataset = "evals/golden_dataset_v2/qa_pairs.json"
    if os.path.exists(old_dataset):
        with open(old_dataset, "r", encoding="utf-8") as f:
            try:
                existing_data = json.load(f)
            except Exception:
                pass

    # Combinamos (podemos adaptarlo al schema de DeepEval)
    combined = existing_data + dataset
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(combined, f, ensure_ascii=False, indent=2)
        
    print(f"Exportado {len(dataset)} registros nuevos de feedback.")
    print(f"Total dataset combinado guardado en {output_path} ({len(combined)} registros).")

if __name__ == "__main__":
    export_golden_dataset()
