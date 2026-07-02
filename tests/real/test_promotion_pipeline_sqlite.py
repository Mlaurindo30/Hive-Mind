"""K3 real tests for Knowledge Intake + Promotion over SQLite.

These tests use the real UMC schema/migrations. They do not call LLMs or mock
the database: K3's first contract is deterministic intake/promotion that keeps
raw observations intact, creates typed candidates, promotes durable knowledge,
and quarantines structurally invalid input.
"""
from __future__ import annotations

import json

import pytest


@pytest.mark.real
def test_promotion_pipeline_promotes_discovery_without_losing_raw(real_db):
    from core.knowledge.promotion import promote_pending_observations

    raw_content = "Discovery K3: model config fixed, CLI sync completed, next step is K3 pipeline."
    real_db.execute(
        """
        INSERT INTO observations(
            id, project, type, title, content, archived, metadata, workspace_id
        )
        VALUES (?, ?, ?, ?, ?, 0, ?, ?)
        """,
        (
            "obs-k3-discovery",
            "Hive-Mind",
            "discovery",
            "K3 discovery bundle",
            raw_content,
            json.dumps(
                {
                    "source_kind": "discovery",
                    "facts": ["snowflake-arctic-embed2 is the canonical embedding model"],
                    "decisions": ["K2 VectorBackend uses seven canonical collections"],
                    "learned": ["Graphiti retry logs must go to stderr"],
                    "narrative": "Investigated K2 failures and isolated Ollama/service causes.",
                    "concepts": ["K2", "VectorBackend", "Milvus"],
                    "evidence": {
                        "files": ["docs/12-knowledge-implementation-plan.md"],
                        "commands": ["./tests/run_all.sh"],
                    },
                    "next_steps": ["Implement K3 promotion pipeline"],
                },
                ensure_ascii=False,
            ),
            "team-a",
        ),
    )
    real_db.commit()

    report = promote_pending_observations(real_db, limit=10, apply=True)

    assert report["observations"] == 1
    assert report["candidates"] >= 5
    assert report["promoted"] >= 4
    assert report["quarantined"] == 0

    obs = real_db.execute(
        "SELECT content, archived, neuron_id FROM observations WHERE id = ?",
        ("obs-k3-discovery",),
    ).fetchone()
    assert obs["content"] == raw_content
    assert obs["archived"] == 1
    assert obs["neuron_id"]

    candidate_rows = real_db.execute(
        """
        SELECT knowledge_type, project, workspace_id, evidence_json, neuron_id
        FROM knowledge_candidates
        WHERE source_id = ?
        ORDER BY knowledge_type
        """,
        ("obs-k3-discovery",),
    ).fetchall()
    types = {row["knowledge_type"] for row in candidate_rows}
    assert {
        "decision",
        "fact",
        "learning",
        "next_step",
        "rationale",
    }.issubset(types)
    assert {row["workspace_id"] for row in candidate_rows} == {"team-a"}
    assert all("docs/12-knowledge-implementation-plan.md" in row["evidence_json"] for row in candidate_rows)

    neurons = real_db.execute(
        """
        SELECT id, type, metadata, workspace_id
        FROM neurons
        WHERE id IN (
            SELECT neuron_id FROM knowledge_candidates WHERE source_id = ? AND neuron_id IS NOT NULL
        )
        """,
        ("obs-k3-discovery",),
    ).fetchall()
    assert {row["type"] for row in neurons} >= {"decision", "fact", "learning", "rationale"}
    assert {row["workspace_id"] for row in neurons} == {"team-a"}
    assert all(json.loads(row["metadata"])["source_observation_id"] == "obs-k3-discovery" for row in neurons)

    goals = real_db.execute("SELECT id, description, status FROM goals").fetchall()
    assert any("Implement K3 promotion pipeline" in row["description"] for row in goals)


@pytest.mark.real
def test_promotion_pipeline_quarantines_structural_errors_and_preserves_raw(real_db):
    from core.knowledge.promotion import promote_pending_observations

    real_db.execute(
        """
        INSERT INTO observations(id, project, type, title, content, archived, metadata)
        VALUES (?, ?, ?, ?, ?, 0, ?)
        """,
        (
            "obs-k3-bad",
            "Hive-Mind",
            "discovery",
            "",
            "",
            json.dumps({"source_kind": "discovery"}, ensure_ascii=False),
        ),
    )
    real_db.commit()

    report = promote_pending_observations(real_db, limit=10, apply=True)

    assert report["observations"] == 1
    assert report["promoted"] == 0
    assert report["quarantined"] == 1
    obs = real_db.execute(
        "SELECT content, archived, metadata, neuron_id FROM observations WHERE id = ?",
        ("obs-k3-bad",),
    ).fetchone()
    assert obs["content"] == ""
    assert obs["archived"] == 2
    assert obs["neuron_id"] is None
    metadata = json.loads(obs["metadata"])
    assert metadata["quarantine"]["retry_policy"] == "manual_fix_required"
    assert "sem conteúdo" in metadata["quarantine"]["reason"]


@pytest.mark.real
def test_promotion_pipeline_promotes_claude_mem_change_observation(real_db):
    from core.knowledge.promotion import promote_pending_observations

    raw_content = "Integrated install-ide-hooks.ts into install.sh main workflow."
    real_db.execute(
        """
        INSERT INTO observations(id, project, type, title, content, archived, metadata)
        VALUES (?, ?, ?, ?, ?, 0, ?)
        """,
        (
            "cm-change-observation",
            "Hive-Mind",
            "change",
            "Integrated install hooks",
            raw_content,
            json.dumps(
                {
                    "source": "claude-mem-bridge",
                    "source_kind": "change",
                    "source_id": "claude-mem:observations:545",
                },
                ensure_ascii=False,
            ),
        ),
    )
    real_db.commit()

    report = promote_pending_observations(real_db, limit=10, apply=True)

    # Governança: change do bridge sem artefatos (files/commands/source_uri)
    # classifica como hypothesis e aguarda a drenagem — não promove na hora.
    assert report["observations"] == 1
    assert report["quarantined"] == 0
    assert report["promoted"] == 0
    assert report["held_hypothesis"] == 1
    obs = real_db.execute(
        "SELECT archived, neuron_id FROM observations WHERE id = ?",
        ("cm-change-observation",),
    ).fetchone()
    assert obs["archived"] == 1
    assert obs["neuron_id"] is None

    candidate = real_db.execute(
        """
        SELECT knowledge_type, source_id, status, confidence, risk
        FROM knowledge_candidates WHERE source_id = ?
        """,
        ("cm-change-observation",),
    ).fetchone()
    assert candidate is not None
    assert candidate["knowledge_type"] == "operational_fact"
    assert candidate["status"] == "held"
    assert candidate["confidence"] == "hypothesis"
    assert candidate["risk"] == "low"

    # Drenagem (janela zerada) promove o candidato held e materializa o neuron.
    from core.knowledge.promotion import promote_held_candidates

    drain = promote_held_candidates(real_db, min_age_days=0)
    assert drain["promoted"] == 1
    promoted = real_db.execute(
        "SELECT status, neuron_id, ttl_review FROM knowledge_candidates WHERE source_id = ?",
        ("cm-change-observation",),
    ).fetchone()
    assert promoted["status"] == "promoted"
    assert promoted["neuron_id"]
    assert promoted["ttl_review"]
    neuron = real_db.execute(
        "SELECT type, metadata FROM neurons WHERE id = ?",
        (promoted["neuron_id"],),
    ).fetchone()
    assert neuron["type"] == "operational_fact"
    assert json.loads(neuron["metadata"])["governance"]["confidence"] == "hypothesis"


@pytest.mark.real
def test_promotion_pipeline_promotes_files_docs_code_and_summaries(real_db, tmp_path):
    from core.knowledge.promotion import promote_files

    doc = tmp_path / "docs" / "design.md"
    code = tmp_path / "core" / "worker.py"
    summary = tmp_path / "cerebro" / "cerebelo" / "semanal" / "2026-W26.md"
    doc.parent.mkdir(parents=True)
    code.parent.mkdir(parents=True)
    summary.parent.mkdir(parents=True)
    doc.write_text("# Design\n\nDocumento de arquitetura K3.", encoding="utf-8")
    code.write_text("def run_k3():\n    return 'ok'\n", encoding="utf-8")
    summary.write_text("# Semana 26\n\nK3 avançou com promoção tipada.", encoding="utf-8")

    report = promote_files(
        real_db,
        [doc, code, summary],
        project="Hive-Mind",
        workspace_id="team-files",
        apply=True,
    )

    assert report["files"] == 3
    assert report["candidates"] == 3
    assert report["promoted"] == 3
    rows = real_db.execute(
        """
        SELECT knowledge_type, workspace_id, neuron_id
        FROM knowledge_candidates
        WHERE workspace_id = 'team-files'
        """
    ).fetchall()
    assert {row["knowledge_type"] for row in rows} == {
        "document_chunk",
        "code_symbol",
        "project_status",
    }
    assert all(row["neuron_id"] for row in rows)
