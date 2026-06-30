"""Real K5 cadence tests: session -> monthly/yearly -> summary_vectors.

These tests use real subprocesses, a real temporary UMC SQLite database and
Ollama-backed embeddings/LLM calls. They intentionally avoid mocks.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"


def _run(script: str, *args: str, env: dict[str, str], timeout: int = 180) -> subprocess.CompletedProcess:
    full_env = os.environ.copy()
    full_env.update(env)
    full_env["PYTHONPATH"] = str(PROJECT_ROOT)
    return subprocess.run(
        [str(PYTHON if PYTHON.exists() else sys.executable), str(PROJECT_ROOT / script), *args],
        cwd=PROJECT_ROOT,
        env=full_env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _seed_tmp_hive(tmp_path: Path) -> Path:
    """Create a minimal project-local Hive-Mind layout with real templates/data."""
    home = tmp_path / "hive"
    core_dir = home / "core"
    core_dir.mkdir(parents=True)
    (core_dir / "umc_schema.sql").write_text(
        (PROJECT_ROOT / "core" / "umc_schema.sql").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    modelos = home / "cerebro" / "tronco" / "modelos"
    modelos.mkdir(parents=True)
    for name in ("session-log.md", "daily-log.md"):
        src = PROJECT_ROOT / "cerebro" / "tronco" / "modelos" / name
        (modelos / name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    session = home / "cerebro" / "cerebelo" / "sessoes" / "2026" / "01" / "02" / "2026-01-02-1000-k5-real.md"
    session.parent.mkdir(parents=True, exist_ok=True)
    session.write_text(
        """---
type: session-log
date: 2026-01-02
session_id: k5-real
description: K5 real cadence seed
consolidated: true
---
# K5 real cadence seed

## Ações
- Implementou cadencia mensal e anual.

## Resumo
- K5 validou cadência semanal, decisões e riscos.
- Manter summaries como fontes, não como fatos automáticos.
- Cadência precisa preservar evidência e evitar duplicação.
- Implementar mensal e anual.
""",
        encoding="utf-8",
    )
    return home


def _env(home: Path) -> dict[str, str]:
    return {
        "SINAPSE_HOME": str(home),
        "HIVE_DREAMER_PROVIDER": "ollama",
        "HIVE_DREAMER_MODEL": "qwen2.5:3b",
        "HIVE_SESSION_SUMMARIZER_PROVIDER": "ollama",
        "HIVE_SESSION_SUMMARIZER_MODEL": "qwen2.5:3b",
        "HIVE_DAILY_WRITER_PROVIDER": "ollama",
        "HIVE_DAILY_WRITER_MODEL": "qwen2.5:3b",
        "HIVE_WEEKLY_SYNTHESIZER_PROVIDER": "ollama",
        "HIVE_WEEKLY_SYNTHESIZER_MODEL": "qwen2.5:3b",
        "HIVE_MONTHLY_SYNTHESIZER_PROVIDER": "ollama",
        "HIVE_MONTHLY_SYNTHESIZER_MODEL": "qwen2.5:3b",
        "HIVE_YEARLY_SYNTHESIZER_PROVIDER": "ollama",
        "HIVE_YEARLY_SYNTHESIZER_MODEL": "qwen2.5:3b",
        "OLLAMA_EMBED_MODEL": "snowflake-arctic-embed2:latest",
        "HIVE_CRDT_SYNC": "0",
    }


@pytest.mark.real
@pytest.mark.requires_service("ollama")
def test_monthly_and_yearly_synthesizers_write_cerebelo_and_summary_vectors(tmp_path, monkeypatch):
    home = _seed_tmp_hive(tmp_path)
    env = _env(home)

    daily = _run("scripts/dream/daily_writer.py", "--date", "2026-01-02", "--no-llm", env=env)
    assert daily.returncode == 0, f"stdout={daily.stdout}\nstderr={daily.stderr}"
    daily_path = home / "cerebro" / "cerebelo" / "diario" / "2026" / "01" / "2026-01-02.md"
    assert daily_path.exists()

    weekly = _run("scripts/dream/weekly_synthesizer.py", "--year", "2026", "--week", "1", "--real", env=env)
    assert weekly.returncode == 0, f"stdout={weekly.stdout}\nstderr={weekly.stderr}"
    weekly_path = home / "cerebro" / "cerebelo" / "semanal" / "2026-W01.md"
    assert weekly_path.exists()

    monthly = _run("scripts/dream/monthly_synthesizer.py", "--month", "2026-01", "--real", env=env)
    assert monthly.returncode == 0, f"stdout={monthly.stdout}\nstderr={monthly.stderr}"

    monthly_path = home / "cerebro" / "cerebelo" / "mensal" / "2026-01.md"
    assert monthly_path.exists()
    monthly_text = monthly_path.read_text(encoding="utf-8")
    assert "type: monthly-summary" in monthly_text
    assert "cadence: monthly" in monthly_text
    assert "source_id:" in monthly_text
    assert "parent_summary_id:" in monthly_text
    assert "llm_role: monthly_synthesizer" in monthly_text
    assert "## Decisões Duráveis" in monthly_text
    assert "## Aprendizados Duráveis" in monthly_text
    assert "## Riscos Persistentes" in monthly_text
    assert "## Metas" in monthly_text

    yearly = _run("scripts/dream/yearly_synthesizer.py", "--year", "2026", "--real", env=env)
    assert yearly.returncode == 0, f"stdout={yearly.stdout}\nstderr={yearly.stderr}"

    yearly_path = home / "cerebro" / "cerebelo" / "anual" / "2026.md"
    assert yearly_path.exists()
    yearly_text = yearly_path.read_text(encoding="utf-8")
    assert "type: yearly-summary" in yearly_text
    assert "cadence: yearly" in yearly_text
    assert "llm_role: yearly_synthesizer" in yearly_text
    assert "## Princípios Duráveis" in yearly_text
    assert "## Lições Aprendidas" in yearly_text

    import core.database as db
    from core.vector_backend import SQLiteVecBackend
    monkeypatch.setattr(db, "DB_PATH", str(home / "hive_mind.db"))
    conn = db.get_connection()
    try:
        db.ensure_migrations(conn)
        backend = SQLiteVecBackend(conn)
        assert backend.count("summary_vectors") >= 4
        sources = {
            row["source_uri"]
            for row in conn.execute(
                "SELECT source_uri FROM vector_metadata WHERE collection='summary_vectors'"
            ).fetchall()
        }
        assert str(daily_path) in sources
        assert str(weekly_path) in sources
        assert str(monthly_path) in sources
        assert str(yearly_path) in sources
    finally:
        conn.close()
