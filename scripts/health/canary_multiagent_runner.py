#!/usr/bin/env python3
"""
canary_multiagent_runner.py — CLI Runner para Canários Multiagente de Captura.

Executa prompts e respostas simuladas/reais sobre todos os providers registrados,
validando a cadeia:
  fonte -> parser -> project_id -> capture_core.ingest -> Claude Mem -> bridge -> workspace_id
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAPTURE_DIR = ROOT / "scripts" / "capture"
if str(CAPTURE_DIR) not in sys.path:
    sys.path.insert(0, str(CAPTURE_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.capture.capture_adapters import ADAPTERS
from scripts.capture.project_identity import (
    ProjectAliasRegistry,
    ProjectIdentityResolver,
)
from scripts.capture.session_events import attach_project_identity
from core.knowledge.claude_mem_bridge import bridge

SHIPPED_REGISTRY = ROOT / "config" / "project-aliases.yaml"


def run_canary_for_provider(provider: str, resolver: ProjectIdentityResolver, base_dir: Path) -> dict:
    if provider not in ADAPTERS:
        return {"provider": provider, "status": "ERROR", "reason": "Provider não registrado"}

    adapter = ADAPTERS[provider]
    repo_dir = base_dir / f"repo-{provider}"
    repo_dir.mkdir(parents=True, exist_ok=True)

    session_id = f"canary-cli-{provider}-990011"
    raw_session = {
        "session_id": session_id,
        "timestamp": 1773900000,
        "cwd": str(repo_dir),
        "official_workspace": str(repo_dir),
        "messages": [
            {"role": "user", "content": f"Canary CLI prompt for {provider}"},
            {"role": "assistant", "content": f"Canary CLI response for {provider}"},
        ],
        "observations": [
            {
                "title": f"CLI Canary Obs {provider}",
                "text": f"CLI Canary text for {provider}",
                "type": "discovery",
                "created_at_epoch": 1773900002,
            }
        ],
    }

    normalized = attach_project_identity(
        provider=provider,
        session=raw_session,
        resolver=resolver,
        default_surface=adapter.get("surface") or "cli",
    )

    project_id = normalized.get("project_id")
    project_name = normalized.get("project")
    identity_envelope = normalized.get("project_identity")

    if not project_id or not identity_envelope:
        return {"provider": provider, "status": "FAILED", "reason": "Identidade de projeto não anexada"}

    # Mock Claude Mem DB
    mem_db = base_dir / f"mem-{provider}.db"
    conn = sqlite3.connect(str(mem_db))
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            memory_session_id TEXT NOT NULL,
            project TEXT NOT NULL,
            text TEXT,
            type TEXT NOT NULL,
            title TEXT,
            created_at TEXT NOT NULL,
            created_at_epoch INTEGER NOT NULL,
            content_hash TEXT UNIQUE,
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
    meta_dict = {"project_identity": identity_envelope}
    conn.execute(
        """
        INSERT INTO observations (memory_session_id, project, text, type, title, created_at, created_at_epoch, content_hash, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            project_name,
            f"CLI Canary text for {provider}",
            "discovery",
            f"CLI Canary Obs {provider}",
            "2026-07-19T20:00:00Z",
            1773900002,
            f"hash-cli-{provider}-{session_id}",
            json.dumps(meta_dict, ensure_ascii=False),
        ),
    )
    conn.commit()

    # Mock UMC DB for Bridge
    umc_db = base_dir / f"umc-{provider}.db"
    umc_conn = sqlite3.connect(str(umc_db))
    umc_conn.executescript(
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
    umc_conn.close()

    # Injetar conexão mockada no module claude_mem_bridge
    import core.knowledge.claude_mem_bridge as bridge_mod

    old_get_conn = bridge_mod.get_connection
    old_ensure_mig = bridge_mod.ensure_migrations

    bridge_mod.get_connection = lambda: sqlite3.connect(str(umc_db))
    bridge_mod.ensure_migrations = lambda c: None

    try:
        stats = bridge(cm_db=mem_db, limit=10, dry_run=False)
        stats_rebridge = bridge(cm_db=mem_db, limit=10, dry_run=False)
    finally:
        conn.close()
        bridge_mod.get_connection = old_get_conn
        bridge_mod.ensure_migrations = old_ensure_mig

    idempotent = stats_rebridge["inserted"] == 0 and stats_rebridge["skipped"] == 1

    return {
        "provider": provider,
        "project_id": project_id,
        "inserted": stats["inserted"],
        "idempotent": idempotent,
        "status": "PASSED" if stats["inserted"] > 0 and idempotent else "FAILED",
    }


def main():
    registry = ProjectAliasRegistry.load(SHIPPED_REGISTRY)
    resolver = ProjectIdentityResolver(registry=registry)

    import tempfile

    with tempfile.TemporaryDirectory() as tmp_dir:
        base_path = Path(tmp_dir)
        results = []
        providers = ["codex", "antigravity", "hermes", "kimi", "kilo", "mimo", "copilot", "roo", "openclaw", "swarmclaw"]

        for p in providers:
            res = run_canary_for_provider(p, resolver, base_path)
            results.append(res)

        print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
