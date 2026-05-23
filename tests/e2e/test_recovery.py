import os
import json
import pytest
import sinapse_memory as sm


class TestRecovery:
    """E4: Recuperação de falhas."""

    def test_corrupted_graph_json_returns_none(self, monkeypatch, tmp_path):
        """graph.json corrompido não crasha."""
        corrupt = tmp_path / "corrupt.json"
        corrupt.write_text("---\ninvalid: [\nyaml json {{{")
        monkeypatch.setattr(sm, "GRAPH_JSON", str(corrupt))
        monkeypatch.setattr(sm, "_graph_cache", {})
        monkeypatch.setattr(sm, "_graph_cache_time", 0)

        result = sm._backend_graphify("query")
        assert result is None

    def test_missing_vault_dir_doesnt_crash_writes(self, temp_vault, monkeypatch):
        """Diretório do vault ausente é criado automaticamente."""
        # Remove the pre-created dirs to simulate missing vault
        import shutil
        shutil.rmtree(temp_vault)
        new_vault = temp_vault + "_fresh"
        os.makedirs(new_vault, exist_ok=True)
        monkeypatch.setattr(sm, "VAULT_DIR", new_vault)
        monkeypatch.setattr(sm, "DECISIONS_DIR", f"{new_vault}/work/active")
        monkeypatch.setattr(sm, "MEMORY_FILE", f"{new_vault}/brain/Current State.md")
        monkeypatch.setattr(sm, "PATTERNS_FILE", f"{new_vault}/brain/Patterns.md")

        sm._post_session_end(session_summary="Recovery test")
        assert os.path.isfile(f"{new_vault}/brain/Current State.md")

    def test_health_check_all_backends_offline(self, monkeypatch):
        """health_check funciona mesmo com tudo offline."""
        monkeypatch.setattr(sm, "GRAPH_JSON", "/nonexistent.json")
        monkeypatch.setattr(sm, "NMEM_BIN", "/nonexistent/nmem")
        monkeypatch.setattr(sm, "_graph_cache", {})
        monkeypatch.setattr(sm, "_graph_cache_time", 0)

        status = sm.health_check()
        assert isinstance(status, dict)
        assert "backends" in status
        # All should be False
        assert status["healthy"] == False

    def test_schema_validation_rejects_bad_graph(self):
        """Validação de schema rejeita graph inválido."""
        bad_graph = {"nodes": "not a list", "links": []}
        assert sm._validate_graph_schema(bad_graph) == False

        bad_graph2 = {"nodes": [{"wrong": "key"}], "links": []}
        assert sm._validate_graph_schema(bad_graph2) == False

        good_graph = {"nodes": [{"label": "x", "id": "y"}], "links": []}
        assert sm._validate_graph_schema(good_graph) == True
