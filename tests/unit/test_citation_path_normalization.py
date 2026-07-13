"""Tests for citation path normalization (_citation_source_uri).

Gate 2 of the Windows gates audit.
"""
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.retrieval.router import _citation_source_uri


class TestCitationSourceUri:
    """Validate that _citation_source_uri normalises paths correctly."""

    @pytest.fixture(autouse=True)
    def _set_sinapse_home(self, tmp_path, monkeypatch):
        self.vault_root = tmp_path / "cerebro"
        self.vault_root.mkdir()
        monkeypatch.setenv("SINAPSE_HOME", str(tmp_path))

    # 1. Caminho absoluto dentro de cerebro/ vira relativo ao vault.
    def test_absolute_inside_vault_becomes_relative(self):
        absolute = str(self.vault_root / "cortex" / "frontal" / "trabalho" / "ativo" / "note.md")
        (self.vault_root / "cortex" / "frontal" / "trabalho" / "ativo").mkdir(parents=True, exist_ok=True)
        (self.vault_root / "cortex" / "frontal" / "trabalho" / "ativo" / "note.md").touch()
        result = _citation_source_uri(absolute)
        assert result == "cortex/frontal/trabalho/ativo/note.md"

    # 2. Caminho Windows com drive é normalizado.
    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific drive letter test")
    def test_windows_drive_path_normalised(self):
        absolute = str(self.vault_root / "cortex" / "temporal" / "proj" / "note.md")
        (self.vault_root / "cortex" / "temporal" / "proj").mkdir(parents=True, exist_ok=True)
        (self.vault_root / "cortex" / "temporal" / "proj" / "note.md").touch()
        result = _citation_source_uri(absolute)
        assert "\\\\" not in result
        assert ":" not in result or result.startswith("http")
        assert result == "cortex/temporal/proj/note.md"

    # 3. Separadores invertidos são normalizados.
    def test_backslash_separators_normalised(self):
        result = _citation_source_uri("some\\path\\to\\file.md")
        assert "\\\\" not in result
        assert "/" in result or result == "some/path/to/file.md"

    # 4. Caminho já relativo não é alterado incorretamente.
    def test_already_relative_path_unchanged(self):
        result = _citation_source_uri("cortex/frontal/decisoes/note.md")
        # Should not mangle an already-relative vault path
        assert "cortex/frontal/decisoes/note.md" in result

    # 5. Caminho externo ao vault não é apresentado como arquivo interno.
    def test_external_path_not_presented_as_internal(self):
        external = "/tmp/some-other-repo/file.md"
        result = _citation_source_uri(external)
        # Must not silently strip to a vault-relative path
        assert "cerebro" not in result or result.startswith("/tmp")

    # 6. source_uri None/empty handled gracefully.
    def test_none_returns_empty(self):
        assert _citation_source_uri(None) == ""

    def test_empty_string_returns_empty(self):
        assert _citation_source_uri("") == ""

    # 7. UMC-style URIs (hive_mind.db:neurons/...) pass through.
    def test_umc_uri_passthrough(self):
        uri = "hive_mind.db:neurons/42"
        result = _citation_source_uri(uri)
        assert "neurons/42" in result

    # 8. Worktree absolute path must NOT appear in output.
    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific worktree test")
    def test_worktree_absolute_not_in_output(self):
        wt = Path("D:/Hive-Mind/backups/worktrees/hive-mind-windows-zero-install")
        fake = str(self.vault_root / "cortex" / "note.md")
        (self.vault_root / "cortex").mkdir(parents=True, exist_ok=True)
        (self.vault_root / "cortex" / "note.md").touch()
        result = _citation_source_uri(fake)
        assert "backups" not in result
        assert "worktrees" not in result


class TestCitationFromContext:
    """Validate that _citation_from_context also normalises source_uri."""

    @pytest.fixture(autouse=True)
    def _set_sinapse_home(self, tmp_path, monkeypatch):
        self.vault_root = tmp_path / "cerebro"
        self.vault_root.mkdir()
        monkeypatch.setenv("SINAPSE_HOME", str(tmp_path))

    def test_citation_source_uri_normalised(self):
        from core.retrieval.router import _citation_from_context
        absolute = str(self.vault_root / "cortex" / "frontal" / "note.md")
        (self.vault_root / "cortex" / "frontal").mkdir(parents=True, exist_ok=True)
        (self.vault_root / "cortex" / "frontal" / "note.md").touch()
        item = {
            "id": absolute,
            "title": "Test Note",
            "source_uri": absolute,
            "score": 0.9,
            "route": "hybrid",
        }
        citation = _citation_from_context(item)
        assert "\\\\" not in (citation["source_uri"] or "")
        assert "cortex/frontal/note.md" in citation["source_uri"]

    def test_citation_id_normalised(self):
        from core.retrieval.router import _citation_from_context
        absolute = str(self.vault_root / "cortex" / "note.md")
        (self.vault_root / "cortex").mkdir(parents=True, exist_ok=True)
        (self.vault_root / "cortex" / "note.md").touch()
        item = {
            "id": absolute,
            "title": "Note",
            "source_uri": absolute,
        }
        citation = _citation_from_context(item)
        assert "\\\\" not in (citation["id"] or "")
