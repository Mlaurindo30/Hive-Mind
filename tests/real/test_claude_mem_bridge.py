"""K4 real tests for the Claude-Mem promotion bridge.

Uses real SQLite files for both sides:
- source: a claude-mem shaped database with observations, discoveries and
  session_summaries;
- target: the real Hive-Mind UMC schema from migrations.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _create_claude_mem_db(path: Path) -> None:
    conn = _connect(path)
    conn.executescript(
        """
        CREATE TABLE observations (
            id INTEGER PRIMARY KEY,
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
            content_hash TEXT,
            generated_by_model TEXT,
            relevance_count INTEGER DEFAULT 0,
            merged_into_project TEXT,
            agent_type TEXT,
            agent_id TEXT,
            metadata TEXT
        );
        CREATE TABLE discoveries (
            id INTEGER PRIMARY KEY,
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
            content_hash TEXT
        );
        CREATE TABLE session_summaries (
            id INTEGER PRIMARY KEY,
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
    conn.execute(
        """
        INSERT INTO observations(
            id, memory_session_id, project, text, type, title, facts, narrative,
            concepts, files_read, files_modified, created_at, created_at_epoch,
            content_hash, metadata
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            10,
            "s-1",
            "Hive-Mind",
            "Raw discovery observation text",
            "discovery",
            "Bridge observation discovery",
            json.dumps(["Observation fact promoted"], ensure_ascii=False),
            "Observation investigation rationale",
            json.dumps(["bridge", "discovery"], ensure_ascii=False),
            json.dumps(["docs/12-knowledge-implementation-plan.md"], ensure_ascii=False),
            json.dumps(["core/knowledge/claude_mem_bridge.py"], ensure_ascii=False),
            "2026-06-29T10:00:00Z",
            100,
            "obs-rich-hash",
            json.dumps({"workspace_id": "ws-observation"}, ensure_ascii=False),
        ),
    )
    conn.execute(
        """
        INSERT INTO discoveries(
            id, memory_session_id, project, title, facts, narrative, learned,
            decisions, next_steps, files_read, created_at, created_at_epoch,
            content_hash
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            20,
            "s-2",
            "Hive-Mind",
            "Explicit discovery row",
            json.dumps(["Discovery table fact"], ensure_ascii=False),
            "Discovery table investigation rationale",
            json.dumps(["Discovery table learning"], ensure_ascii=False),
            json.dumps(["Discovery table decision"], ensure_ascii=False),
            json.dumps(["Discovery table next step"], ensure_ascii=False),
            json.dumps(["docs/11-knowledge-promotion-architecture.md"], ensure_ascii=False),
            "2026-06-29T10:05:00Z",
            105,
            "disc-row-hash",
        ),
    )
    conn.execute(
        """
        INSERT INTO session_summaries(
            id, memory_session_id, project, request, investigated, learned,
            completed, decisions, next_steps, files_read, files_edited, notes,
            created_at, created_at_epoch
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            30,
            "s-3",
            "Hive-Mind",
            "Implement K4 bridge",
            "Investigated claude-mem schemas and bridge gaps",
            json.dumps(["Session learned item"], ensure_ascii=False),
            json.dumps(["Session completed item"], ensure_ascii=False),
            json.dumps(["Session decision item"], ensure_ascii=False),
            json.dumps(["Session next step item"], ensure_ascii=False),
            json.dumps(["scripts/services/claude_mem_bridge.py"], ensure_ascii=False),
            json.dumps(["core/knowledge/claude_mem_bridge.py"], ensure_ascii=False),
            "Session notes",
            "2026-06-29T10:10:00Z",
            110,
        ),
    )
    conn.commit()
    conn.close()


@pytest.mark.real
def test_claude_mem_bridge_imports_rich_sources_and_promotes_fields(real_db, tmp_path):
    from core.knowledge.claude_mem_bridge import bridge
    from core.knowledge.promotion import promote_pending_observations

    cm_db = tmp_path / "claude-mem.db"
    _create_claude_mem_db(cm_db)

    stats = bridge(cm_db=cm_db, limit=20)

    assert stats["scanned"] == 3
    assert stats["inserted"] == 3
    assert stats["skipped"] == 0
    assert stats["by_source"] == {
        "discoveries": 1,
        "observations": 1,
        "session_summaries": 1,
    }

    rows = real_db.execute(
        """
        SELECT id, project, type, title, content, metadata, archived, workspace_id
        FROM observations
        WHERE id LIKE 'cm-%'
        ORDER BY id
        """
    ).fetchall()
    assert len(rows) == 3
    assert {row["project"] for row in rows} == {"Hive-Mind"}
    assert {row["archived"] for row in rows} == {0}
    metadata_by_table = {
        json.loads(row["metadata"])["source_table"]: json.loads(row["metadata"])
        for row in rows
    }
    assert metadata_by_table["discoveries"]["source_id"] == "claude-mem:discoveries:20"
    assert metadata_by_table["session_summaries"]["source_id"] == "claude-mem:session_summaries:30"

    report = promote_pending_observations(real_db, limit=10, apply=True)

    assert report["observations"] == 3
    assert report["quarantined"] == 0
    assert report["promoted"] >= 9
    candidates = real_db.execute(
        """
        SELECT knowledge_type, source_id, content, evidence_json
        FROM knowledge_candidates
        ORDER BY source_id, knowledge_type, content
        """
    ).fetchall()
    types = {row["knowledge_type"] for row in candidates}
    assert {
        "decision",
        "fact",
        "learning",
        "next_step",
        "operational_fact",
        "rationale",
    }.issubset(types)
    assert any(row["content"] == "Session completed item" and row["knowledge_type"] == "operational_fact" for row in candidates)
    assert any(row["content"] == "Session decision item" and row["knowledge_type"] == "decision" for row in candidates)
    assert any("core/knowledge/claude_mem_bridge.py" in row["evidence_json"] for row in candidates)

    goals = real_db.execute("SELECT description FROM goals").fetchall()
    assert any("Session next step item" in row["description"] for row in goals)


@pytest.mark.real
def test_claude_mem_bridge_filters_by_source_ids_and_temporal_window(real_db, tmp_path):
    from core.knowledge.claude_mem_bridge import bridge

    cm_db = tmp_path / "claude-mem.db"
    _create_claude_mem_db(cm_db)

    stats = bridge(
        cm_db=cm_db,
        source_ids=["claude-mem:session_summaries:30"],
        since_epoch=105,
        until_epoch=120,
    )

    assert stats["scanned"] == 1
    assert stats["inserted"] == 1
    row = real_db.execute("SELECT type, metadata FROM observations").fetchone()
    assert row["type"] == "session_summary"
    assert json.loads(row["metadata"])["source_id"] == "claude-mem:session_summaries:30"

    stats2 = bridge(cm_db=cm_db, source_ids=["claude-mem:session_summaries:30"])
    assert stats2["inserted"] == 0
    assert stats2["skipped"] == 1
