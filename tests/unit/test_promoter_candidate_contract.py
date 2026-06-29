"""K3/B4: existing promoters expose candidate-only outputs.

The specialized promoters keep their current materialization behavior, but K3
requires each one to also expose a deterministic candidate-only path with
workspace_id so intake/promotion can orchestrate them without forcing writes.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from core.knowledge.intake import KnowledgeCandidate
from core.schemas.pattern_models import Pattern
from scripts.knowledge import (
    conflict_detector,
    decision_promoter,
    drift_detector,
    pattern_distiller,
    sector_classifier,
    topic_consolidator,
    work_tracker,
)


@pytest.fixture()
def temporal_vault(tmp_path):
    temporal = tmp_path / "temporal"
    path = temporal / "Hive-Mind" / "k3" / "neuronio-dec.md"
    path.parent.mkdir(parents=True)
    data = {"type": "decision", "integrity_hash": "dec-hash"}
    path.write_text(
        "---\n" + yaml.dump(data, allow_unicode=True, sort_keys=False) + "---\n"
        "# Decidir K3\n\nImplementar candidate-only.\n",
        encoding="utf-8",
    )
    return temporal


def test_decision_promoter_candidate_only(temporal_vault):
    candidates = decision_promoter.collect_candidates(temporal_vault, workspace_id="team-a")
    assert len(candidates) == 1
    assert isinstance(candidates[0], KnowledgeCandidate)
    assert candidates[0].knowledge_type == "decision"
    assert candidates[0].workspace_id == "team-a"


def test_pattern_distiller_candidate_only():
    pattern = Pattern(
        title="Rodar teste real antes do commit",
        slug="teste-real-antes-commit",
        context="Mudança de pipeline",
        steps=["rodar teste real", "corrigir falhas"],
        when_to_use="Antes de commit",
        confidence=0.9,
    )
    candidates = pattern_distiller.patterns_to_candidates([pattern], workspace_id="team-a")
    assert candidates[0].knowledge_type == "learning"
    assert candidates[0].workspace_id == "team-a"
    assert "rodar teste real" in candidates[0].content


def test_work_tracker_candidate_only():
    candidates = work_tracker.next_steps_to_candidates(
        [{"item": "Implementar K3", "session": "sessao-1"}],
        workspace_id="team-a",
    )
    assert candidates[0].knowledge_type == "next_step"
    assert candidates[0].workspace_id == "team-a"


def test_drift_detector_candidate_only(tmp_path):
    path = tmp_path / "neuronio-old.md"
    item = {
        "path": path,
        "project": "Hive-Mind",
        "topic": "k3",
        "type": "decision",
        "age_days": 200,
    }
    candidates = drift_detector.drift_to_candidates([], [item], workspace_id="team-a")
    assert candidates[0].knowledge_type == "project_status"
    assert candidates[0].workspace_id == "team-a"
    assert "stale" in candidates[0].metadata["drift_state"]


def test_conflict_detector_candidate_only():
    candidates = conflict_detector.conflicts_to_candidates(
        [{"a": "neuron-a", "b": "neuron-b", "explanation": "contradição"}],
        workspace_id="team-a",
    )
    assert candidates[0].knowledge_type == "rationale"
    assert candidates[0].workspace_id == "team-a"
    assert "contradição" in candidates[0].content


def test_sector_classifier_candidate_only(tmp_path):
    path = tmp_path / "neuronio-sector.md"
    path.write_text("# Nota\nConteúdo")
    candidate = sector_classifier.sector_update_candidate(
        path,
        ["infra", "memory"],
        project="Hive-Mind",
        workspace_id="team-a",
    )
    assert candidate.knowledge_type == "project_status"
    assert candidate.workspace_id == "team-a"
    assert "infra" in candidate.content


def test_topic_consolidator_candidate_only():
    candidate = topic_consolidator.merge_proposal_candidate(
        "Hive-Mind",
        ["vector_backend", "vectors"],
        "vector_backend",
        rationale="nomes equivalentes",
        workspace_id="team-a",
    )
    assert candidate.knowledge_type == "rationale"
    assert candidate.workspace_id == "team-a"
    assert "vector_backend" in candidate.content
