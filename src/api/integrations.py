from fastapi import APIRouter, Depends, HTTPException, Header
from datetime import datetime
from typing import List, Optional
import os
from src.api.dependencies import get_status_provider
from pydantic import BaseModel

router = APIRouter()

# --- Seguridad Interna (compartida con Airflow) ---
INTERNAL_API_KEY = os.getenv("AIRFLOW_INTERNAL_API_KEY", "")

def verify_internal_key(x_internal_key: str = Header(...)):
    """Valida que el request viene de Airflow usando una API Key compartida."""
    if not INTERNAL_API_KEY:
        raise HTTPException(status_code=500, detail="AIRFLOW_INTERNAL_API_KEY no configurada en el servidor")
    if x_internal_key != INTERNAL_API_KEY:
        raise HTTPException(status_code=403, detail="Forbidden: API Key inválida")


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

class NotionUpdatePayload(BaseModel):
    user_id: str
    access_token: Optional[str] = None
    database_id: Optional[str] = None

@router.put("/integrations/notion/update")
async def update_notion_sync(payload: NotionUpdatePayload, status_provider = Depends(get_status_provider)):
    """Actualiza las credenciales o el ID de origen de una integración de Notion existente."""
    try:
        updated = status_provider.update_integration(
            user_id=payload.user_id,
            source_type="notion",
            access_token=payload.access_token,
            source_id=payload.database_id
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Integración no encontrada")
        return {"msg": "Integración actualizada con éxito"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class IntegrationUpdatePayload(BaseModel):
    user_id: str
    source_type: str
    access_token: Optional[str] = None
    source_id: Optional[str] = None

@router.put("/integrations/update")
async def update_user_integration(payload: IntegrationUpdatePayload, status_provider = Depends(get_status_provider)):
    """Actualiza una integración de cualquier tipo (Notion, Obsidian, etc.)."""
    try:
        updated = status_provider.update_integration(
            user_id=payload.user_id,
            source_type=payload.source_type,
            access_token=payload.access_token,
            source_id=payload.source_id
        )
        if not updated:
            raise HTTPException(status_code=404, detail=f"Integración '{payload.source_type}' no encontrada para el usuario")
        return {"msg": f"Integración {payload.source_type} actualizada con éxito"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/internal/sync/notion/targets", dependencies=[Depends(verify_internal_key)])
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

@router.post("/internal/sync/notion/update_state", dependencies=[Depends(verify_internal_key)])
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


# --- Nuevos Endpoints: Notion BFS Crawler ---

class NotionPageUpsertPayload(BaseModel):
    user_id: str
    notion_id: str
    parent_id: Optional[str] = None
    object_type: str  # 'page' | 'database'
    last_edited_time: str  # ISO 8601 string
    file_hash: Optional[str] = None
    is_archived: int = 0


@router.post("/internal/sync/notion/upsert_page", dependencies=[Depends(verify_internal_key)])
async def upsert_notion_page(
    payload: NotionPageUpsertPayload,
    status_provider=Depends(get_status_provider),
):
    """Airflow reporta el estado de cada página/db descubierta durante el crawler BFS."""
    try:
        status_provider.upsert_notion_page_metadata(
            user_id=payload.user_id,
            notion_id=payload.notion_id,
            parent_id=payload.parent_id,
            object_type=payload.object_type,
            last_edited_time=datetime.fromisoformat(payload.last_edited_time),
            file_hash=payload.file_hash,
            is_archived=payload.is_archived,
        )
        return {"msg": "Page metadata upserted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class NotionPageUpdateItem(BaseModel):
    notion_id: str
    parent_id: Optional[str] = None
    object_type: str
    last_edited_time: str
    file_hash: Optional[str] = None
    is_archived: int = 0


class NotionBatchUpsertPayload(BaseModel):
    user_id: str
    updates: List[NotionPageUpdateItem]


@router.post("/internal/sync/notion/batch_upsert", dependencies=[Depends(verify_internal_key)])
async def batch_upsert_notion_page(
    payload: NotionBatchUpsertPayload,
    status_provider=Depends(get_status_provider),
):
    """Actualiza múltiples registros de metadatos en una sola transacción."""
    try:
        updates = [u.dict() for u in payload.updates]
        status_provider.batch_upsert_notion_metadata(
            user_id=payload.user_id,
            updates=updates
        )
        return {"msg": f"{len(updates)} pages metadata upserted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class NotionArchivePagesPayload(BaseModel):
    user_id: str
    notion_ids: List[str]


@router.post("/internal/sync/notion/archive_pages", dependencies=[Depends(verify_internal_key)])
async def archive_notion_pages(
    payload: NotionArchivePagesPayload,
    status_provider=Depends(get_status_provider),
):
    """Airflow notifica los IDs huérfanos (páginas que ya no existen en el workspace)."""
    try:
        status_provider.mark_notion_pages_archived(
            user_id=payload.user_id,
            notion_ids=payload.notion_ids,
        )
        return {"msg": f"{len(payload.notion_ids)} pages archived", "archived_ids": payload.notion_ids}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/internal/sync/notion/page_meta/{user_id}/{notion_id}", dependencies=[Depends(verify_internal_key)])
async def get_notion_page_meta(
    user_id: str,
    notion_id: str,
    status_provider=Depends(get_status_provider),
):
    """Devuelve los metadatos guardados de una pagina/db de Notion (para CDC del crawler)."""
    data = status_provider.get_notion_page_metadata(user_id=user_id, notion_id=notion_id)
    if not data:
        return {}
    if data.get("last_edited_time"):
        data["last_edited_time"] = data["last_edited_time"].isoformat()
    return data


@router.get("/internal/sync/notion/all_page_ids/{user_id}", dependencies=[Depends(verify_internal_key)])
async def get_all_notion_page_ids(
    user_id: str,
    status_provider=Depends(get_status_provider),
):
    """Devuelve todos los notion_ids activos guardados para un usuario (orphan detection)."""
    notion_ids = status_provider.get_all_notion_page_ids_for_user(user_id=user_id)
    return {"user_id": user_id, "notion_ids": notion_ids}


@router.delete("/integrations/notion/{user_id}")
async def delete_notion_integration(
    user_id: str, 
    source_id: Optional[str] = None,
    status_provider = Depends(get_status_provider)
):
    """Elimina una o todas las integraciones de Notion de un usuario."""
    try:
        deleted = status_provider.delete_integration(user_id=user_id, source_type="notion", source_id=source_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Integración no encontrada")
        return {"msg": "Integración eliminada con éxito"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/internal/sync/notion/metadata/{user_id}", dependencies=[Depends(verify_internal_key)])
async def get_notion_metadata(user_id: str, status_provider = Depends(get_status_provider)):
    """Devuelve todo el mapa de metadatos de Notion para un usuario (para depuración)."""
    try:
        return status_provider.get_all_notion_metadata_for_user(user_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/internal/sync/notion/reset/{user_id}", dependencies=[Depends(verify_internal_key)])
async def reset_notion_sync(user_id: str, status_provider = Depends(get_status_provider)):
    """Limpia el estado de CDC para que la próxima sincronización sea Full Load."""
    try:
        status_provider.reset_notion_metadata(user_id)
        return {"msg": "Notion sync state reset successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
