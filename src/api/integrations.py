from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime
from src.api.dependencies import get_status_provider
from pydantic import BaseModel

router = APIRouter()

class NotionRegisterPayload(BaseModel):
    user_id: str
    access_token: str
    database_id: str

@router.post("/integrations/notion/register")
async def register_notion_sync(payload: NotionRegisterPayload, status_provider = Depends(get_status_provider)):
    """Registra de manera segura una integración de Notion y habilita su recolección en Airflow"""
    try:
        status_provider.register_integration(
            user_id=payload.user_id,
            source_type="notion",
            access_token=payload.access_token,
            source_id=payload.database_id
        )
        return {"msg": "Notion registrado con éxito"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/internal/sync/notion/targets")
async def get_notion_sync_targets(status_provider = Depends(get_status_provider)):
    """
    Endpoint interno consumido por Airflow.
    Hace JOIN entre las credenciales encriptadas y el estado actual de sincronización.
    """
    try:
        return status_provider.get_sync_targets(source_type="notion")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class SyncStateUpdatePayload(BaseModel):
    user_id: str
    status: str
    last_sync_at: str

@router.post("/internal/sync/notion/update_state")
async def update_notion_sync_state(payload: SyncStateUpdatePayload, status_provider = Depends(get_status_provider)):
    """Actualiza el timestamp del último CDC exitoso tras completarse la tarea de Airflow."""
    try:
        last_sync_time = datetime.fromisoformat(payload.last_sync_at)
        status_provider.update_sync_state(
            user_id=payload.user_id,
            source_type="notion",
            status=payload.status,
            last_sync_at=last_sync_time
        )
        return {"msg": "State updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
