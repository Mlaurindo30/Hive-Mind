import json
import pytest
from unittest.mock import patch, MagicMock
from sinapse_memory import _backend_claude_mem


class TestBackendClaudeMem:
    """U2: Backend claude-mem — busca HTTP"""

    def test_worker_unreachable_returns_none(self):
        """U2.1: Worker offline retorna None sem crash."""
        with patch("sinapse_memory.urlopen", side_effect=OSError("connection refused")):
            result = _backend_claude_mem("test query")
            assert result is None

    def test_semantic_search_returns_context(self):
        """U2.2: Busca semântica retorna contexto formatado."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "context": "Informação relevante sobre o projeto",
            "count": 3,
        }).encode()
        mock_response.__enter__.return_value = mock_response

        with patch("sinapse_memory.urlopen", return_value=mock_response):
            result = _backend_claude_mem("projeto")
            assert result is not None
            assert result["source"] == "claude-mem (semantic)"
            assert result["count"] == 3
            assert len(result["observations"]) > 0

    def test_fts5_fallback_when_semantic_fails(self):
        """U2.3: FTS5 é usado quando busca semântica falha."""
        call_count = [0]

        def side_effect(req, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise OSError("semantic endpoint down")
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps({
                "items": [
                    {"title": "Nota 1", "excerpt": "Conteúdo da nota"},
                    {"title": "Nota 2", "excerpt": "Mais conteúdo"},
                ],
            }).encode()
            mock_resp.__enter__.return_value = mock_resp
            return mock_resp

        with patch("sinapse_memory.urlopen", side_effect=side_effect):
            result = _backend_claude_mem("test")
            assert result is not None
            assert result["source"] == "claude-mem (FTS5)"
            assert result["count"] == 2

    def test_invalid_json_returns_none(self):
        """U2.4: JSON inválido retorna None sem crash."""
        mock_response = MagicMock()
        mock_response.read.return_value = b"not valid json {{{"
        mock_response.__enter__.return_value = mock_response

        with patch("sinapse_memory.urlopen", return_value=mock_response):
            result = _backend_claude_mem("query")
            assert result is None

    def test_empty_context_returns_none(self):
        """U2.5: Contexto vazio (count=0) retorna None."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "context": "",
            "count": 0,
        }).encode()
        mock_response.__enter__.return_value = mock_response

        with patch("sinapse_memory.urlopen", return_value=mock_response):
            result = _backend_claude_mem("query")
            assert result is None

    def test_respects_max_observations(self, monkeypatch):
        """U2.6: Respeita MAX_OBSERVATIONS no FTS5."""
        monkeypatch.setattr("sinapse_memory.MAX_OBSERVATIONS", 2)
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "context": "",
            "count": 0,
        }).encode()
        mock_response.__enter__.return_value = mock_response

        # First call fails (empty context), second succeeds via FTS5
        call_count = [0]

        def side_effect(req, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                mock_resp = MagicMock()
                mock_resp.read.return_value = json.dumps({"context": "", "count": 0}).encode()
                mock_resp.__enter__.return_value = mock_resp
                return mock_resp
            else:
                items = [
                    {"title": f"Item {i}", "excerpt": f"Excerpt {i}"}
                    for i in range(5)
                ]
                mock_resp = MagicMock()
                mock_resp.read.return_value = json.dumps({"items": items}).encode()
                mock_resp.__enter__.return_value = mock_resp
                return mock_resp

        with patch("sinapse_memory.urlopen", side_effect=side_effect):
            result = _backend_claude_mem("test")
            assert result is not None
            assert len(result["observations"]) <= 2

    def test_null_items_still_returns_none(self):
        """U2.7: Items nulos (FTS5) retorna None."""
        call_count = [0]

        def side_effect(req, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise OSError("down")
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps({"items": []}).encode()
            mock_resp.__enter__.return_value = mock_resp
            return mock_resp

        with patch("sinapse_memory.urlopen", side_effect=side_effect):
            result = _backend_claude_mem("test")
            assert result is None
