import pytest
import uuid
from unittest.mock import MagicMock, patch, AsyncMock
from src.service.orchestrator import IngestionOrchestrator


@pytest.fixture
def mock_status_provider():
    return MagicMock()


@pytest.fixture
def mock_storage_provider():
    return MagicMock()


@pytest.fixture
def orchestrator(mock_status_provider, mock_storage_provider):
    return IngestionOrchestrator(
        status_provider=mock_status_provider,
        storage_provider=mock_storage_provider
    )


@pytest.mark.asyncio
async def test_orchestrate_ingestion_success(orchestrator, mock_status_provider, mock_storage_provider):
    doc_id = uuid.uuid4()
    filename = "test.txt"
    content = b"test content"

    # Mock the Celery task so it doesn't try to connect to RabbitMQ
    mock_task_result = MagicMock()
    mock_task_result.id = str(doc_id)

    with patch("src.service.orchestrator.process_document_task") as mock_task:
        mock_task.apply_async.return_value = mock_task_result

        result = await orchestrator.orchestrate_ingestion(
            doc_id=doc_id,
            filename=filename,
            content=content
        )

    assert result["doc_id"] == str(doc_id)
    assert result["status"] == "queued"
    mock_status_provider.create_job.assert_called_once()
    mock_storage_provider.upload_file.assert_called_once()
    mock_status_provider.update_status.assert_called_with(doc_id, "queued")


@pytest.mark.asyncio
async def test_orchestrate_ingestion_with_object_name(orchestrator, mock_status_provider, mock_storage_provider):
    """Claim Check: file already in MinIO, only send reference."""
    doc_id = uuid.uuid4()
    filename = "heavy.txt"
    object_name = "user/path/heavy.txt"

    mock_task_result = MagicMock()
    mock_task_result.id = str(doc_id)

    with patch("src.service.orchestrator.process_document_task") as mock_task:
        mock_task.apply_async.return_value = mock_task_result

        result = await orchestrator.orchestrate_ingestion(
            doc_id=doc_id,
            filename=filename,
            object_name=object_name
        )

    assert result["doc_id"] == str(doc_id)
    # No content was passed, so MinIO upload should NOT be called
    mock_storage_provider.upload_file.assert_not_called()
    mock_status_provider.update_status.assert_called_with(doc_id, "queued")


def test_validate_file_extension_error(orchestrator):
    with pytest.raises(ValueError, match="no permitida"):
        orchestrator.validate_file("malicious.exe", b"content")


def test_validate_file_size_error(orchestrator):
    """Override max_size directly on the instance to test validation."""
    orchestrator.max_size = 10  # 10 bytes limit
    with pytest.raises(ValueError, match="excede"):
        orchestrator.validate_file("test.txt", b"this content is way too long")


def test_validate_allowed_file(orchestrator):
    """Should not raise for allowed extensions."""
    try:
        orchestrator.validate_file("test.pdf", b"small")
    except ValueError:
        pytest.fail("validate_file raised ValueError for an allowed extension")
