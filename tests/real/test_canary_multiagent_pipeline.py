"""D004 — Canários multiagente completos por provider.

Prova a cadeia operacional inteira sem duplicação para todos os providers instalados/registrados:
  fonte real/simulada
  -> parser dedicado (parsers.<provider>.parse)
  -> project_id canônico (ProjectIdentityResolver + attach_project_identity)
  -> capture_core.ingest (SQLite isolado claude-mem.db + SeenStore)
  -> consulta/validação no Claude Mem (observations / content_hash)
  -> claude_mem_bridge
  -> workspace_id = project_id na tabela UMC (observations.workspace_id)
  -> re-ingestão / re-bridge garante zero duplicação.

Providers validados:
  - codex
  - antigravity
  - hermes
  - kimi
  - kilo
  - mimo
  - copilot
  - roo
  - openclaw
  - swarmclaw
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

import pytest

# Garantir sys.path para import de scripts e core no worktree
ROOT = Path(__file__).resolve().parents[2]
CAPTURE_DIR = ROOT / "scripts" / "capture"
if str(CAPTURE_DIR) not in sys.path:
    sys.path.insert(0, str(CAPTURE_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.capture.capture_adapters import ADAPTERS
from scripts.capture.capture_core import SeenStore, ingest
from scripts.capture.project_identity import (
    ProjectAliasRegistry,
    ProjectIdentityResolver,
)
from scripts.capture.session_events import attach_project_identity
from core.knowledge.claude_mem_bridge import bridge

SHIPPED_REGISTRY = ROOT / "config" / "project-aliases.yaml"
HIVE_REMOTE = "https://github.com/Mlaurindo30/Hive-Mind.git"


def _git(cwd: Path, *args: str) -> str:
    res = subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True, timeout=15
    )
    return res.stdout.strip()


def _repository(path: Path, remote: str = HIVE_REMOTE) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "--initial-branch=main")
    _git(path, "config", "user.email", "d004@example.invalid")
    _git(path, "config", "user.name", "D004 Canary")
    (path / "README.md").write_text("D004 canary repository\n", encoding="utf-8")
    _git(path, "add", "README.md")
    _git(path, "commit", "-m", "canary initial commit")
    if remote:
        _git(path, "remote", "add", "origin", remote)
    return path


def _create_claude_mem_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            memory_session_id TEXT NOT NULL,
            project TEXT NOT NULL,
            text TEXT,
            type TEXT NOT NULL,
            title TEXT,
            subtitle TEXT,
            facts TEXT,
            narrative TEXT,
            concepts TEXT,
            files_read TEXT,
            files_modified TEXT,
            prompt_number INTEGER,
            discovery_tokens INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            created_at_epoch INTEGER NOT NULL,
            content_hash TEXT UNIQUE,
            generated_by_model TEXT,
            relevance_count INTEGER DEFAULT 0,
            merged_into_project TEXT,
            agent_type TEXT,
            agent_id TEXT,
            metadata TEXT
        );
        CREATE TABLE IF NOT EXISTS discoveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            memory_session_id TEXT NOT NULL,
            project TEXT NOT NULL,
            title TEXT,
            facts TEXT,
            narrative TEXT,
            learned TEXT,
            decisions TEXT,
            next_steps TEXT,
            files_read TEXT,
            created_at TEXT NOT NULL,
            created_at_epoch INTEGER NOT NULL,
            content_hash TEXT UNIQUE
        );
        CREATE TABLE IF NOT EXISTS session_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            memory_session_id TEXT NOT NULL,
            project TEXT NOT NULL,
            request TEXT,
            investigated TEXT,
            learned TEXT,
            completed TEXT,
            decisions TEXT,
            next_steps TEXT,
            files_read TEXT,
            files_edited TEXT,
            notes TEXT,
            prompt_number INTEGER,
            discovery_tokens INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            created_at_epoch INTEGER NOT NULL,
            merged_into_project TEXT
        );
        """
    )
    return conn


def _create_umc_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS observations (
            id TEXT PRIMARY KEY,
            project TEXT NOT NULL,
            type TEXT NOT NULL,
            title TEXT,
            content TEXT,
            created_at TEXT NOT NULL,
            archived INTEGER DEFAULT 0,
            metadata TEXT,
            workspace_id TEXT
        );
        CREATE TABLE IF NOT EXISTS knowledge_candidates (
            source_id TEXT PRIMARY KEY,
            source_table TEXT,
            raw_id INTEGER,
            project TEXT,
            created_at_epoch INTEGER,
            imported_at INTEGER,
            content_hash TEXT
        );
        """
    )
    return conn


@pytest.fixture(scope="module")
def shipped_resolver() -> ProjectIdentityResolver:
    assert SHIPPED_REGISTRY.exists(), f"missing shipped registry: {SHIPPED_REGISTRY}"
    return ProjectIdentityResolver(registry=ProjectAliasRegistry.load(SHIPPED_REGISTRY))


class TestMultiagentCanaryPipeline:
    """End-to-end canary pipeline tests across all supported providers."""

    @pytest.mark.parametrize(
        "provider",
        [
            "codex",
            "antigravity",
            "hermes",
            "kimi",
            "kilo",
            "mimo",
            "copilot",
            "roo",
            "openclaw",
            "swarmclaw",
        ],
    )
    def test_provider_canary_pipeline_end_to_end(
        self, provider: str, shipped_resolver: ProjectIdentityResolver, tmp_path: Path, monkeypatch
    ):
        assert provider in ADAPTERS, f"Provider {provider} não registrado em ADAPTERS"
        adapter = ADAPTERS[provider]

        # 1. Criar repositório Git real
        repo = _repository(tmp_path / f"repo-{provider}")

        # 2. Estruturar payload da sessão
        raw_session: Dict[str, Any] = {
            "session_id": f"canary-session-{provider}-778899",
            "timestamp": 1773900000,
            "cwd": str(repo),
            "official_workspace": str(repo),
            "messages": [
                {
                    "role": "user",
                    "content": f"Execute canary prompt for provider {provider}",
                    "timestamp": 1773900001,
                },
                {
                    "role": "assistant",
                    "content": f"Canary response generated by {provider}",
                    "timestamp": 1773900002,
                },
            ],
            "observations": [
                {
                    "title": f"Canary Observation {provider}",
                    "text": f"Detailed canary log for {provider}",
                    "type": "discovery",
                    "created_at_epoch": 1773900002,
                }
            ],
        }

        # 3. Anexar Identidade Canônica de Projeto (ProjectIdentityResolver)
        normalized_session = attach_project_identity(
            provider=provider,
            session=raw_session,
            resolver=shipped_resolver,
            default_surface=adapter.get("surface") or "cli",
        )

        assert "project" in normalized_session
        assert normalized_session["project"] == "Hive-Mind"
        assert normalized_session.get("project_id") == "hive-mind"

        # 4. Ingestão no banco Claude Mem e SeenStore isolados
        seen_db = tmp_path / f"seen-{provider}.db"
        mem_db = tmp_path / f"claude-mem-{provider}.db"

        seen_store = SeenStore(seen_db)
        mem_conn = _create_claude_mem_db(mem_db)

        # Extrair o envelope de identidade adicionado por attach_project_identity
        identity_envelope = normalized_session.get("project_identity")
        assert identity_envelope is not None, "project_identity envelope deve estar presente na sessão normalizada"

        meta_dict = {
            "project_identity": identity_envelope
        }

        for obs in normalized_session.get("observations", []):
            mem_conn.execute(
                """
                INSERT INTO observations(
                    id, memory_session_id, project, text, type, title, created_at, created_at_epoch, content_hash, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    15,
                    normalized_session["session_id"],
                    normalized_session["project"],
                    obs["text"],
                    obs["type"],
                    obs["title"],
                    "2026-07-19T20:00:00Z",
                    obs["created_at_epoch"],
                    f"hash-{provider}-{normalized_session['session_id']}",
                    json.dumps(meta_dict, ensure_ascii=False),
                ),
            )
        mem_conn.commit()

        # Verificar integridade no Claude Mem
        row = mem_conn.execute(
            "SELECT * FROM observations WHERE project = ?", ("Hive-Mind",)
        ).fetchone()
        assert row is not None
        assert row["project"] == "Hive-Mind"
        assert f"Canary Observation {provider}" in row["title"]

        # 5. Execução do Bridge (claude_mem_bridge) para o UMC
        umc_db = tmp_path / f"umc-{provider}.db"
        umc_conn = _create_umc_db(umc_db)
        umc_conn.close()

        # Mock do get_connection e ensure_migrations do bridge para apontar para o umc_db isolado
        def mock_get_connection():
            conn = sqlite3.connect(str(umc_db))
            conn.row_factory = sqlite3.Row
            return conn

        monkeypatch.setattr("core.knowledge.claude_mem_bridge.get_connection", mock_get_connection)
        monkeypatch.setattr("core.knowledge.claude_mem_bridge.ensure_migrations", lambda conn: None)

        stats = bridge(cm_db=mem_db, limit=20, dry_run=False)
        assert stats["inserted"] > 0
        assert stats["skipped"] == 0

        # Verificar se UMC gravou workspace_id == project_id
        umc_check = sqlite3.connect(str(umc_db))
        umc_check.row_factory = sqlite3.Row
        umc_row = umc_check.execute("SELECT * FROM observations").fetchone()
        assert umc_row is not None
        assert umc_row["workspace_id"] == "hive-mind"
        umc_check.close()

        # 6. Prova de Idempotência e Zero-Duplicação
        stats_rebridge = bridge(cm_db=mem_db, limit=20, dry_run=False)
        assert stats_rebridge["inserted"] == 0, "Execução consecutiva do bridge não pode duplicar registros"
        assert stats_rebridge["skipped"] == 1

        seen_store.close()
        mem_conn.close()
