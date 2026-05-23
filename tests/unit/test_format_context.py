import pytest
from sinapse_memory import _format_context


class TestFormatContext:
    """U6: Formatação de contexto para injeção no prompt"""

    def test_format_claude_mem_context(self):
        """U6.1: Contexto claude-mem formatado corretamente."""
        ctx = {
            "source": "claude-mem (semantic)",
            "observations": [
                {"content": "Informação sobre o projeto Thoth"},
            ],
            "count": 1,
            "query": "thoth",
        }
        result = _format_context(ctx)
        assert "[Sinapse" in result
        assert "claude-mem" in result
        assert "Thoth" in result

    def test_format_graphify_context(self):
        """U6.2: Contexto graphify formatado corretamente."""
        ctx = {
            "source": "graphify (structural)",
            "nodes": [
                {"label": "thoth", "type": "document", "source": "thoth.md"},
            ],
            "edges": [
                {"source": "thoth", "target": "vps", "relation": "related_to"},
            ],
        }
        result = _format_context(ctx)
        assert "thoth" in result
        assert "document" in result
        assert "related_to" in result
        assert "↳" in result

    def test_format_respects_max_chars(self, monkeypatch):
        """U6.3: Respeita MAX_CONTEXT_CHARS."""
        monkeypatch.setattr("sinapse_memory.MAX_CONTEXT_CHARS", 50)
        ctx = {
            "source": "test",
            "observations": [
                {"content": "X" * 500},
            ],
        }
        result = _format_context(ctx)
        assert len(result) <= 50 + 7  # +7 for "\n[...]"
        assert "[...]" in result

    def test_format_empty_observations(self):
        """U6.4: Contexto sem observations não quebra."""
        ctx = {
            "source": "test",
            "observations": [],
            "nodes": [],
            "edges": [],
        }
        result = _format_context(ctx)
        assert "[Sinapse" in result
        assert "test" in result
