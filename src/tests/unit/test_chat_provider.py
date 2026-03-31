import pytest
import uuid
from unittest.mock import patch, MagicMock
from src.providers.database.chat_provider import ChatProvider

@patch("src.providers.database.chat_provider.get_engine")
@patch("src.providers.database.chat_provider.sessionmaker")
@patch("src.providers.database.chat_provider.Base.metadata.create_all")
def test_create_chat(mock_create_all, mock_sessionmaker, mock_get_engine):
    mock_session = MagicMock()
    mock_sessionmaker.return_value = MagicMock(return_value=mock_session)
    mock_session.query().filter().first.return_value = None

    provider = ChatProvider()
    thread_id = uuid.uuid4()
    
    result = provider.create_chat(user_id="user1", title="Test Chat", thread_id=thread_id)
    
    assert result == thread_id
    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()

@patch("src.providers.database.chat_provider.get_engine")
@patch("src.providers.database.chat_provider.sessionmaker")
@patch("src.providers.database.chat_provider.Base.metadata.create_all")
def test_get_user_chats(mock_create_all, mock_sessionmaker, mock_get_engine):
    mock_session = MagicMock()
    mock_sessionmaker.return_value = MagicMock(return_value=mock_session)
    
    mock_chat = MagicMock()
    mock_chat.id = uuid.uuid4()
    mock_chat.title = "Test"
    mock_chat.created_at.isoformat.return_value = "2024-01-01T00:00:00"
    
    mock_session.query().filter().order_by().all.return_value = [mock_chat]
    
    provider = ChatProvider()
    results = provider.get_user_chats("user1")
    
    assert len(results) == 1
    assert results[0]["title"] == "Test"

@patch("src.providers.database.chat_provider.get_engine")
@patch("src.providers.database.chat_provider.sessionmaker")
@patch("src.providers.database.chat_provider.Base.metadata.create_all")
def test_add_message_and_get_messages(mock_create_all, mock_sessionmaker, mock_get_engine):
    mock_session = MagicMock()
    mock_sessionmaker.return_value = MagicMock(return_value=mock_session)
    
    provider = ChatProvider()
    
    # Test Add
    thread_id = uuid.uuid4()
    provider.add_message(thread_id=thread_id, role="user", content="Hello")
    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()
    
    # Test Get
    mock_msg = MagicMock()
    mock_msg.id = uuid.uuid4()
    mock_msg.role = "user"
    mock_msg.content = "Hello"
    mock_msg.parts = None
    mock_msg.created_at.isoformat.return_value = "2024-01-01"
    
    mock_session.query().filter().order_by().all.return_value = [mock_msg]
    msgs = provider.get_chat_messages(thread_id)
    assert len(msgs) == 1
    assert msgs[0]["content"] == "Hello"
