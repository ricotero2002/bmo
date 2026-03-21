import pytest
import uuid
from unittest.mock import patch, MagicMock

# Importamos la tarea que queremos probar
from src.workers.tasks import delete_document_task, TRANSIENT_EXCEPTIONS, PERMANENT_EXCEPTIONS

@patch("src.workers.tasks.StatusProvider")
@patch("src.workers.tasks.StorageFactory.get_storage")
@patch("src.workers.tasks.VectorStoreFactory.get_provider")
@patch("src.workers.tasks.RecordManagerFactory.get_manager")
def test_delete_document_task_success(
    mock_get_manager, 
    mock_get_provider, 
    mock_get_storage, 
    mock_status_provider
):
    """
    Testea el camino feliz o 'Happy Path':
    - Se borran los chunks de Chroma/OpenSearch.
    - Se eliminan del RecordManager.
    - Se borra de S3/MinIO.
    - Se actualiza a estado 'deleted'.
    """
    # Setup Mocks
    mock_status = MagicMock()
    mock_status_provider.return_value = mock_status
    
    mock_storage = MagicMock()
    mock_get_storage.return_value = mock_storage
    
    mock_vector = MagicMock()
    mock_vector_provider = MagicMock()
    mock_vector_provider.getVectorStore.return_value = mock_vector
    mock_get_provider.return_value = mock_vector_provider
    
    mock_manager = MagicMock()
    mock_get_manager.return_value = mock_manager
    
    # Setup Datos
    doc_id = str(uuid.uuid4())
    user_id = "test_user_777"
    
    # Simulamos que RecordManager devuelve 2 chunks asociados al doc_id
    mock_manager.list_keys.return_value = ["chunk-1", "chunk-2"]
    # Ejecutamos la tarea invocándola con .run() para evitar el wrapper de Celery
    result = delete_document_task(doc_id=doc_id, user_id=user_id)
    
    # -- Assertions (Validaciones) --
    
    # 1. Verifica que haya marcado la bbdd como "deleting" preventivamente
    mock_status.update_status.assert_any_call(uuid.UUID(doc_id), "deleting")
    
    # 2. Verifica vector store y record manager
    mock_manager.list_keys.assert_called_once_with(group_ids=[doc_id])
    mock_vector.delete.assert_called_once_with(ids=["chunk-1", "chunk-2"])
    mock_manager.delete_keys.assert_called_once_with(["chunk-1", "chunk-2"])
    
    # 3. Verifica el borrado físico (S3/MinIO usa user_id/doc_id de ruta)
    mock_storage.delete_file.assert_called_once_with(f"{user_id}/{doc_id}")
    
    # 4. Verifica que se haya completado el proceso
    mock_status.update_status.assert_any_call(uuid.UUID(doc_id), "deleted")
    
    assert result == {
        "status": "deleted",
        "doc_id": doc_id,
    }


@patch("src.workers.tasks.StatusProvider")
@patch("src.workers.tasks.StorageFactory.get_storage")
@patch("src.workers.tasks.VectorStoreFactory.get_provider")
@patch("src.workers.tasks.RecordManagerFactory.get_manager")
def test_delete_document_task_already_deleted_vectors(
    mock_get_manager, 
    mock_get_provider, 
    mock_get_storage, 
    mock_status_provider
):
    """
    Testea lo que pasa cuando el flujo es idempotente porque el Vector Store ya las había borrado, 
    pero no encuentra los chunks (ej. el sistema falló a la mitad la primera vez).
    """
    mock_status = mock_status_provider.return_value
    mock_storage = mock_get_storage.return_value
    mock_vector = mock_get_provider.return_value.getVectorStore.return_value
    mock_manager = mock_get_manager.return_value
    
    doc_id = str(uuid.uuid4())
    
    # No hay chunks (idempotencia)
    mock_manager.list_keys.return_value = []
    
    result = delete_document_task(doc_id=doc_id, user_id=None)
    
    # Validamos que omitió hacer delete al vector store por estar vacío
    mock_vector.delete.assert_not_called()
    mock_manager.delete_keys.assert_not_called()
    
    # Aun así fue a borrar el PDF/Storage de todas formas (sin user_id el path es solo doc_id)
    mock_storage.delete_file.assert_called_once_with(doc_id)
    
    assert result["status"] == "deleted"


@patch("src.workers.tasks.StatusProvider")
@patch("src.workers.tasks.StorageFactory.get_storage")
@patch("src.workers.tasks.VectorStoreFactory.get_provider")
@patch("src.workers.tasks.RecordManagerFactory.get_manager")
def test_delete_document_task_unexpected_error_raises_exception(
    mock_get_manager, 
    mock_get_provider, 
    mock_get_storage, 
    mock_status_provider
):
    """
    Testea la reciente implementación donde los errores no manejados hacen un `raise exc`
    para mandarse a la Dead Letter Queue, a la vez que marcan como 'dead' en la DB.
    """
    mock_status = mock_status_provider.return_value
    mock_storage = mock_get_storage.return_value
    mock_manager = mock_get_manager.return_value
    
    doc_id = str(uuid.uuid4())
    
    # Para aislar, no importan las keys
    mock_manager.list_keys.return_value = []
    
    # Hacemos que la DB salte con una Excepción inesperada (por ejemplo al listar keys)
    mock_manager.list_keys.side_effect = Exception("Database connection lost")
    
    with pytest.raises(Exception, match="Database connection lost"):
        delete_document_task(doc_id=doc_id)
        
    # Validamos que se haya marcado en la base de datos antes de irse a Dead Letter.
    # El status_provider actualiza la DB a dead con un trace de "UNEXPECTED_ERROR:"
    mock_status.update_status.assert_called_with(
        uuid.UUID(doc_id), 
        "dead", 
        error_msg="UNEXPECTED_ERROR: Database connection lost"
    )
