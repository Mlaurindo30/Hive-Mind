import json
import pytest
from unittest.mock import patch
from sinapse_memory import _backend_neural_memory


class TestBackendNmem:
    """U3: Backend NeuralMemory — busca associativa"""

    def test_binary_missing_returns_none(self, monkeypatch):
        """U3.1: Binário ausente retorna None."""
        monkeypatch.setattr("sinapse_memory.NMEM_BIN", "/nonexistent/nmem")
        result = _backend_neural_memory("test")
        assert result is None

    def test_json_mode_returns_parsed_result(self, monkeypatch):
        """U3.2: Modo --json retorna resultado parseado."""
        mock_output = json.dumps([
            {"content": "Memória 1 sobre projeto", "confidence": 0.9},
            {"content": "Memória 2 sobre arquitetura", "confidence": 0.7},
        ])
        mock_result = type("Result", (), {
            "returncode": 0,
            "stdout": mock_output,
            "stderr": "",
        })()

        with patch("subprocess.run", return_value=mock_result):
            monkeypatch.setattr("sinapse_memory.NMEM_BIN", "/usr/bin/nmem")
            monkeypatch.setattr("os.path.isfile", lambda _: True)
            monkeypatch.setattr("os.access", lambda _1, _2: True)
            result = _backend_neural_memory("projeto")
            assert result is not None
            assert result["source"].startswith("neural-memory")
            assert len(result["observations"]) == 2
            assert result["observations"][0]["confidence"] == 0.9

    def test_json_mode_dict_with_memories_key(self, monkeypatch):
        """U3.3: JSON no formato {memories: [...]}."""
        mock_output = json.dumps({
            "memories": [
                {"content": "Aprendizado 1", "confidence": 0.8},
            ]
        })
        mock_result = type("Result", (), {
            "returncode": 0,
            "stdout": mock_output,
            "stderr": "",
        })()

        with patch("subprocess.run", return_value=mock_result):
            monkeypatch.setattr("sinapse_memory.NMEM_BIN", "/usr/bin/nmem")
            monkeypatch.setattr("os.path.isfile", lambda _: True)
            monkeypatch.setattr("os.access", lambda _1, _2: True)
            result = _backend_neural_memory("test")
            assert result is not None
            assert len(result["observations"]) == 1

    def test_fallback_to_text_parser(self, monkeypatch):
        """U3.4: JSON falha, recorre ao parser de texto."""
        # First call: JSON mode fails with invalid JSON
        # Second call: text mode succeeds
        call_index = [0]

        def run_side_effect(args, **kwargs):
            call_index[0] += 1
            if "--json" in args:
                return type("Result", (), {"returncode": 0, "stdout": "not valid json", "stderr": ""})()
            else:
                output = """- Memória relevante sobre deploy
  [note] src=nota1.md · date=2026-01-01 · conf=0.85"""
                return type("Result", (), {"returncode": 0, "stdout": output, "stderr": ""})()

        with patch("subprocess.run", side_effect=run_side_effect):
            monkeypatch.setattr("sinapse_memory.NMEM_BIN", "/usr/bin/nmem")
            monkeypatch.setattr("os.path.isfile", lambda _: True)
            monkeypatch.setattr("os.access", lambda _1, _2: True)
            result = _backend_neural_memory("deploy")
            assert result is not None
            assert len(result["observations"]) > 0

    def test_empty_output_returns_none(self, monkeypatch):
        """U3.5: Output vazio retorna None."""
        mock_result = type("Result", (), {
            "returncode": 0,
            "stdout": "",
            "stderr": "",
        })()

        with patch("subprocess.run", return_value=mock_result):
            monkeypatch.setattr("sinapse_memory.NMEM_BIN", "/usr/bin/nmem")
            monkeypatch.setattr("os.path.isfile", lambda _: True)
            monkeypatch.setattr("os.access", lambda _1, _2: True)
            result = _backend_neural_memory("test")
            assert result is None

    def test_timeout_returns_none(self, monkeypatch):
        """U3.6: Timeout retorna None sem crash."""
        import subprocess

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 5)):
            monkeypatch.setattr("sinapse_memory.NMEM_BIN", "/usr/bin/nmem")
            monkeypatch.setattr("os.path.isfile", lambda _: True)
            monkeypatch.setattr("os.access", lambda _1, _2: True)
            result = _backend_neural_memory("test")
            assert result is None

    def test_respects_max_observations(self, monkeypatch):
        """U3.7: Respeita MAX_OBSERVATIONS."""
        monkeypatch.setattr("sinapse_memory.MAX_OBSERVATIONS", 2)
        mock_output = json.dumps([
            {"content": f"Memória {i}", "confidence": 0.5}
            for i in range(10)
        ])
        mock_result = type("Result", (), {
            "returncode": 0,
            "stdout": mock_output,
            "stderr": "",
        })()

        with patch("subprocess.run", return_value=mock_result):
            monkeypatch.setattr("sinapse_memory.NMEM_BIN", "/usr/bin/nmem")
            monkeypatch.setattr("os.path.isfile", lambda _: True)
            monkeypatch.setattr("os.access", lambda _1, _2: True)
            result = _backend_neural_memory("test")
            assert result is not None
            assert len(result["observations"]) <= 2
