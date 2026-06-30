import json
import os
import subprocess
import sys
import pytest
from pathlib import Path


class TestSinapseWriteCLI:
    """Testes para scripts/services/sinapse-write.py"""

    SCRIPT = Path(__file__).parent.parent.parent / "scripts" / "services" / "sinapse-write.py"

    def test_health_command(self):
        result = subprocess.run(
            [sys.executable, str(self.SCRIPT), "health"],
            capture_output=True, text=True, timeout=30
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "backends" in data
        assert "vault" in data
        assert "plugin" in data

    def test_decision_command(self, tmp_path, monkeypatch, temp_vault):
        monkeypatch.setenv("SINAPSE_HOME", temp_vault)
        monkeypatch.setenv("SINAPSE_DRY_RUN", "1")
        result = subprocess.run(
            [sys.executable, str(self.SCRIPT), "decision",
             "--title", "Test CLI Decision",
             "--content", "Test content from CLI"],
            capture_output=True, text=True, timeout=15
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "saved" in data

    def test_decision_command_no_dryrun(self, temp_vault, monkeypatch):
        monkeypatch.setenv("SINAPSE_HOME", temp_vault)
        result = subprocess.run(
            [sys.executable, str(self.SCRIPT), "decision",
             "--title", "Real Decision Save",
             "--content", "Real content persisted"],
            capture_output=True, text=True, timeout=15
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data.get("saved") is True
        assert data.get("path") is not None
        import os

    def test_learning_command(self, tmp_path, monkeypatch, temp_vault):
        monkeypatch.setenv("SINAPSE_HOME", temp_vault)
        monkeypatch.setenv("SINAPSE_DRY_RUN", "1")
        result = subprocess.run(
            [sys.executable, str(self.SCRIPT), "learning",
             "--title", "CLI Learning Test",
             "--content", "Learning from CLI"],
            capture_output=True, text=True, timeout=15
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "saved" in data

    def test_query_command(self):
        result = subprocess.run(
            [sys.executable, str(self.SCRIPT), "query", "thoth"],
            capture_output=True, text=True, timeout=15
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, dict)

    def test_promotion_command_promotes_pending_observation(self, tmp_path):
        env = os.environ.copy()
        env["SINAPSE_HOME"] = str(tmp_path)
        root = Path(__file__).resolve().parents[2]
        (tmp_path / "core").mkdir(parents=True)
        (tmp_path / "core" / "umc_schema.sql").write_text(
            (root / "core" / "umc_schema.sql").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        setup = """
import json
import core.database as db
db.init_db()
conn = db.get_connection()
conn.execute(
    "INSERT INTO observations(id, project, type, title, content, archived, metadata) VALUES (?, ?, ?, ?, ?, 0, ?)",
    ("cli-promo-obs", "Hive-Mind", "decision", "CLI promotion", "Promover via CLI", json.dumps({"evidence": {"commands": ["sinapse-write promotion"]}})),
)
conn.commit()
conn.close()
"""
        seeded = subprocess.run(
            [sys.executable, "-c", setup],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert seeded.returncode == 0, seeded.stderr or seeded.stdout

        result = subprocess.run(
            [sys.executable, str(self.SCRIPT), "promotion", "--limit", "1"],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )

        assert result.returncode == 0, result.stderr or result.stdout
        data = json.loads(result.stdout)
        assert data["observations"] == 1
        assert data["promoted"] == 1
        assert data["quarantined"] == 0

    def test_session_end_command(self, temp_vault, monkeypatch):
        monkeypatch.setenv("SINAPSE_HOME", temp_vault)
        result = subprocess.run(
            [sys.executable, str(self.SCRIPT), "session-end",
             "--summary", "Test session ended via CLI"],
            capture_output=True, text=True, timeout=15
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data.get("updated") is True

    def test_missing_required_args_fails(self):
        result = subprocess.run(
            [sys.executable, str(self.SCRIPT), "decision", "--title", "Test"],
            capture_output=True, text=True, timeout=15
        )
        assert result.returncode != 0  # missing --content should fail
