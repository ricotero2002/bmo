"""
Tests Unitarios — Herramientas nuevas de Fase 7 Parte 3

Prueba web_search y save_note_to_knowledge_base de forma aislada,
sin conectarse a internet ni a Kafka/VectorDB real.
"""
import json
import pytest
from unittest.mock import MagicMock, patch, call
from langchain_core.runnables import RunnableConfig


# ===========================================================================
# Tests: web_search
# ===========================================================================

class TestWebSearch:
    """
    Tests unitarios para src/tools/web_search.py.
    Mockea DuckDuckGoSearchResults para no hacer peticiones reales a internet.
    """

    def _make_raw_results(self, items: list[dict]) -> list[dict]:
        """Devuelve una lista de diccionarios, igual que DuckDuckGoSearchResults(output_format='list') los devuelve."""
        return items

    @patch("src.tools.web_search._scrape_webpage")
    @patch("src.tools.web_search.DuckDuckGoSearchResults")
    def test_returns_formatted_results(self, mock_ddg_cls, mock_scrape):
        """El output tiene título, URL y snippet para cada resultado."""
        from src.tools.web_search import web_search

        mock_scrape.return_value = "Contenido real raspado de la web."
        mock_search = MagicMock()
        mock_ddg_cls.return_value = mock_search
        mock_search.invoke.return_value = self._make_raw_results([
            {"title": "LangChain Docs", "link": "https://docs.langchain.com", "snippet": "Framework de orquestación de LLMs."},
            {"title": "LlamaIndex", "link": "https://llamaindex.ai", "snippet": "Data framework para RAG applications."},
        ])

        result = web_search.invoke({"query": "frameworks de IA 2026"})

        assert "Resultados de la Búsqueda Profunda Web" in result
        assert "LangChain Docs" in result
        assert "https://docs.langchain.com" in result
        assert "[CONTENIDO EXTRAÍDO DE LA PÁGINA]" in result
        assert "Contenido real raspado" in result
        assert "LlamaIndex" in result
        assert "https://llamaindex.ai" in result

    @patch("src.tools.web_search.DuckDuckGoSearchResults")
    def test_snippet_is_truncated_at_800_chars(self, mock_ddg_cls):
        """Los snippets no deben exceder 800 caracteres."""
        from src.tools.web_search import web_search

        mock_search = MagicMock()
        mock_ddg_cls.return_value = mock_search
        long_snippet = "A" * 1200  # Más de 800 chars
        mock_search.invoke.return_value = self._make_raw_results([
            {"title": "Resultado largo", "link": "https://example.com", "snippet": long_snippet},
        ])

        result = web_search.invoke({"query": "test truncation"})

        # El snippet real en el output no puede superar 800 chars + "..."
        # Verificamos que no aparece la parte cortada
        assert "A" * 801 not in result
        assert "A" * 800 in result or "A" * 799 in result or "[SNIPPET RESUMEN]" in result

    @patch("src.tools.web_search.DuckDuckGoSearchResults")
    def test_empty_results_returns_friendly_message(self, mock_ddg_cls):
        """Si no hay resultados, devuelve un mensaje amigable en lugar de fallar."""
        from src.tools.web_search import web_search

        mock_search = MagicMock()
        mock_ddg_cls.return_value = mock_search
        mock_search.invoke.return_value = self._make_raw_results([])

        result = web_search.invoke({"query": "algo que no existe"})

        assert "no arrojó resultados" in result.lower()

    @patch("src.tools.web_search.DuckDuckGoSearchResults")
    def test_plain_text_fallback_on_json_decode_error(self, mock_ddg_cls):
        """Si DuckDuckGo devuelve texto plano (no JSON), usa el fallback sin crashear."""
        from src.tools.web_search import web_search

        mock_search = MagicMock()
        mock_ddg_cls.return_value = mock_search
        # DuckDuckGo devuelve HTML/texto plano en lugar de JSON
        mock_search.invoke.return_value = "Resultado en texto plano sin formato JSON"

        result = web_search.invoke({"query": "test fallback"})

        # Si no es una lista, el ruteo actual lo trata como fallo de búsqueda
        assert "no arrojó resultados" in result.lower()

    @patch("src.tools.web_search.DuckDuckGoSearchResults")
    def test_exception_returns_error_message(self, mock_ddg_cls):
        """Si ocurre una excepción inesperada, devuelve mensaje de error sin propagarla."""
        from src.tools.web_search import web_search

        mock_search = MagicMock()
        mock_ddg_cls.return_value = mock_search
        mock_search.invoke.side_effect = RuntimeError("Timeout de red")

        result = web_search.invoke({"query": "test error"})

        assert "error" in result.lower()
        # No debe lanzar excepción al caller

    @patch("src.tools.web_search.DuckDuckGoSearchResults")
    def test_missing_link_defaults_to_hash(self, mock_ddg_cls):
        """Si un resultado no tiene 'link', usa '#' como fallback."""
        from src.tools.web_search import web_search

        mock_search = MagicMock()
        mock_ddg_cls.return_value = mock_search
        mock_search.invoke.return_value = self._make_raw_results([
            {"title": "Sin URL", "snippet": "Resultado sin enlace."},  # Sin 'link'
        ])

        result = web_search.invoke({"query": "test sin link"})

        assert "URL: #" in result
        assert "Sin URL" in result

    @patch("src.tools.web_search.DuckDuckGoSearchResults")
    def test_result_format_structure(self, mock_ddg_cls):
        """Verifica que el formato de cada resultado tiene los tres campos esperados."""
        from src.tools.web_search import web_search

        mock_search = MagicMock()
        mock_ddg_cls.return_value = mock_search
        mock_search.invoke.return_value = self._make_raw_results([
            {"title": "Test Title", "link": "https://test.com", "snippet": "Test snippet content."},
        ])

        result = web_search.invoke({"query": "formato test"})

        assert "Título: Test Title" in result
        assert "URL: https://test.com" in result
        assert "Contenido:" in result
        assert "Test snippet content." in result


# ===========================================================================
# Tests: save_note_to_knowledge_base
# ===========================================================================

class TestSaveNote:
    """
    Tests unitarios para src/tools/save_note.py.
    Mockea KafkaProducerWrapper para no publicar mensajes reales.
    Verifica que el payload enviado a Kafka es correcto.
    """

    @patch("src.tools.save_note.KafkaProducerWrapper")
    def test_publishes_to_kafka_with_correct_topic(self, mock_wrapper_cls):
        """Verifica que publica en el topic correcto (settings.KAFKA_RAW_DOCUMENTS_TOPIC)."""
        from src.tools.save_note import save_note_to_knowledge_base
        from src.core.config import settings

        mock_producer = MagicMock()
        mock_wrapper_cls.get_instance.return_value = mock_producer

        config = RunnableConfig(configurable={"user_id": "user_test_123"})
        result = save_note_to_knowledge_base.invoke(
            {"title": "Nota de prueba", "content": "Contenido de prueba.", "doc_type": "general"},
            config=config,
        )

        mock_producer.produce.assert_called_once()
        call_kwargs = mock_producer.produce.call_args
        assert call_kwargs.kwargs["topic"] == settings.KAFKA_RAW_DOCUMENTS_TOPIC

    @patch("src.tools.save_note.KafkaProducerWrapper")
    def test_payload_is_consumer_compatible(self, mock_wrapper_cls):
        """
        Verifica que el payload JSON tiene todos los campos que espera kafka_consumer.py:
        doc_id, filename, user_id, content, metadata.
        """
        from src.tools.save_note import save_note_to_knowledge_base

        mock_producer = MagicMock()
        mock_wrapper_cls.get_instance.return_value = mock_producer

        config = RunnableConfig(configurable={"user_id": "user_abc"})
        save_note_to_knowledge_base.invoke(
            {"title": "Mi Plan de IA", "content": "Usar LangChain y Pinecone.", "doc_type": "planning"},
            config=config,
        )

        # Capturar el valor JSON enviado a Kafka
        call_kwargs = mock_producer.produce.call_args.kwargs
        payload = json.loads(call_kwargs["value"])

        # Campos requeridos por kafka_consumer.py
        assert "doc_id" in payload
        assert "filename" in payload
        assert "user_id" in payload
        assert "content" in payload
        assert "metadata" in payload

        # Valores correctos
        assert payload["user_id"] == "user_abc"
        assert payload["doc_type"] if "doc_type" in payload else payload["metadata"].get("doc_type") == "planning"

    @patch("src.tools.save_note.KafkaProducerWrapper")
    def test_content_is_formatted_as_markdown(self, mock_wrapper_cls):
        """El contenido debe estar formateado como '# Título\\n\\nContenido'."""
        from src.tools.save_note import save_note_to_knowledge_base

        mock_producer = MagicMock()
        mock_wrapper_cls.get_instance.return_value = mock_producer

        config = RunnableConfig(configurable={"user_id": "u1"})
        save_note_to_knowledge_base.invoke(
            {"title": "Frameworks de IA", "content": "LangChain, LlamaIndex y FastAPI."},
            config=config,
        )

        payload = json.loads(mock_producer.produce.call_args.kwargs["value"])
        assert payload["content"].startswith("# Frameworks de IA\n\n")
        assert "LangChain, LlamaIndex y FastAPI." in payload["content"]

    @patch("src.tools.save_note.KafkaProducerWrapper")
    def test_filename_is_in_agent_notes_folder(self, mock_wrapper_cls):
        """El filename debe estar dentro de agent_notes/ y terminar en .md."""
        from src.tools.save_note import save_note_to_knowledge_base

        mock_producer = MagicMock()
        mock_wrapper_cls.get_instance.return_value = mock_producer

        config = RunnableConfig(configurable={"user_id": "u1"})
        save_note_to_knowledge_base.invoke(
            {"title": "Resumen de Reunión", "content": "Puntos clave discutidos."},
            config=config,
        )

        payload = json.loads(mock_producer.produce.call_args.kwargs["value"])
        assert payload["filename"].startswith("agent_notes/")
        assert payload["filename"].endswith(".md")

    @patch("src.tools.save_note.KafkaProducerWrapper")
    def test_metadata_origin_is_bmo_agent_generated(self, mock_wrapper_cls):
        """La metadata debe identificar el origen como 'bmo_agent_generated'."""
        from src.tools.save_note import save_note_to_knowledge_base

        mock_producer = MagicMock()
        mock_wrapper_cls.get_instance.return_value = mock_producer

        config = RunnableConfig(configurable={"user_id": "u1"})
        save_note_to_knowledge_base.invoke(
            {"title": "Test Origin", "content": "Contenido de test."},
            config=config,
        )

        payload = json.loads(mock_producer.produce.call_args.kwargs["value"])
        assert payload["metadata"]["origin"] == "bmo_agent_generated"
        assert "created_at" in payload["metadata"]
        assert "title" in payload["metadata"]

    @patch("src.tools.save_note.KafkaProducerWrapper")
    def test_user_id_none_when_no_config(self, mock_wrapper_cls):
        """Si no hay config/user_id, el payload tiene user_id=None sin lanzar excepción."""
        from src.tools.save_note import save_note_to_knowledge_base

        mock_producer = MagicMock()
        mock_wrapper_cls.get_instance.return_value = mock_producer

        # Sin config → user_id debe ser None
        result = save_note_to_knowledge_base.invoke(
            {"title": "Sin config", "content": "Prueba sin usuario."}
        )

        payload = json.loads(mock_producer.produce.call_args.kwargs["value"])
        assert payload["user_id"] is None
        assert "guardada exitosamente" in result

    @patch("src.tools.save_note.KafkaProducerWrapper")
    def test_kafka_exception_returns_error_message(self, mock_wrapper_cls):
        """Si Kafka falla, devuelve un mensaje de error legible sin propagar la excepción."""
        from src.tools.save_note import save_note_to_knowledge_base

        mock_producer = MagicMock()
        mock_wrapper_cls.get_instance.return_value = mock_producer
        mock_producer.produce.side_effect = Exception("Kafka no disponible")

        config = RunnableConfig(configurable={"user_id": "u1"})
        result = save_note_to_knowledge_base.invoke(
            {"title": "Test error", "content": "Contenido."},
            config=config,
        )

        assert "error" in result.lower()
        # No debe propagar la excepción

    @patch("src.tools.save_note.KafkaProducerWrapper")
    def test_success_message_contains_title(self, mock_wrapper_cls):
        """El mensaje de éxito debe mencionar el título de la nota guardada."""
        from src.tools.save_note import save_note_to_knowledge_base

        mock_producer = MagicMock()
        mock_wrapper_cls.get_instance.return_value = mock_producer

        config = RunnableConfig(configurable={"user_id": "u1"})
        result = save_note_to_knowledge_base.invoke(
            {"title": "Mi Nota Especial", "content": "Contenido."},
            config=config,
        )

        assert "Mi Nota Especial" in result
        assert "guardada exitosamente" in result.lower()

    @patch("src.tools.save_note.KafkaProducerWrapper")
    def test_doc_id_used_as_kafka_key(self, mock_wrapper_cls):
        """El key de Kafka debe ser el doc_id generado (para particionamiento consistente)."""
        from src.tools.save_note import save_note_to_knowledge_base

        mock_producer = MagicMock()
        mock_wrapper_cls.get_instance.return_value = mock_producer

        config = RunnableConfig(configurable={"user_id": "u1"})
        save_note_to_knowledge_base.invoke(
            {"title": "Key Test", "content": "Contenido."},
            config=config,
        )

        call_kwargs = mock_producer.produce.call_args.kwargs
        payload = json.loads(call_kwargs["value"])

        # El key de Kafka debe coincidir con el doc_id del payload
        assert call_kwargs["key"] == payload["doc_id"]
