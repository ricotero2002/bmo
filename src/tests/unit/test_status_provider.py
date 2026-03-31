import pytest
import uuid
from unittest.mock import MagicMock, patch
from src.providers.database.status_provider import StatusProvider

@pytest.fixture
def mock_session():
    return MagicMock()

@pytest.fixture
def status_provider(mock_session):
    with patch("src.providers.database.status_provider.get_engine"), \
         patch("src.providers.database.status_provider.sessionmaker") as mock_sm:
        mock_sm.return_value = lambda: mock_session
        provider = StatusProvider()
        return provider

def test_create_job_idempotency(status_provider, mock_session):
    doc_id = uuid.uuid4()
    filename = "test.txt"
    
    # Simular que NO existe
    mock_session.query.return_value.filter.return_value.first.return_value = None
    
    created_id = status_provider.create_job(filename, doc_id=doc_id)
    
    assert created_id == doc_id
    assert mock_session.add.called
    assert mock_session.commit.called

def test_create_job_already_exists(status_provider, mock_session):
    doc_id = uuid.uuid4()
    
    # Simular que SI existe
    mock_session.query.return_value.filter.return_value.first.return_value = MagicMock()
    
    created_id = status_provider.create_job("test.txt", doc_id=doc_id)
    
    assert created_id == doc_id
    assert not mock_session.add.called # No debería intentar añadirlo de nuevo

def test_update_status(status_provider, mock_session):
    doc_id = uuid.uuid4()
    mock_job = MagicMock()
    mock_job.attempts = 0
    mock_session.query.return_value.filter.return_value.first.return_value = mock_job
    
    status_provider.update_status(doc_id, "failed", error_msg="Error")
    
    assert mock_job.status == "failed"
    assert mock_job.error_msg == "Error"
    assert mock_job.attempts == 1
    assert mock_session.commit.called
