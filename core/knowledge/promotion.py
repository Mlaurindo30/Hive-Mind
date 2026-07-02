"""K3 Knowledge Promotion.

Persiste candidatos tipados no UMC de forma idempotente, preservando raw data.
Esta camada e deterministica: LLMs/promotores especializados entram antes ou
depois como produtores/consumidores de candidatos, nao como requisito para o
contrato basico de promocao.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sqlite3
from typing import Iterable, Any

from core.database import add_column_if_missing
from core.knowledge.intake import (
    CANONICAL_TYPES,
    KnowledgeCandidate,
    StructuralIntakeError,
    normalize_markdown_file,
    normalize_observation,
)


NEURON_TYPES = CANONICAL_TYPES - {"next_step"}

# Governança proporcional ao risco (federated-memory GOVERNANCE.md):
# verified+low promove imediato com TTL de revisão; hypothesis+low aguarda a
# drenagem periódica; risk=high só promove com aprovação explícita.
TTL_REVIEW_DAYS = 90
HELD_MIN_AGE_DAYS = 7


def governance_enabled() -> bool:
    """Kill-switch: HIVE_GOVERNANCE_RISK=0/false/off volta ao promote-all."""
    return os.environ.get("HIVE_GOVERNANCE_RISK", "1").strip().lower() not in {
        "0", "false", "off", "no",
    }


def _governance_action(candidate: KnowledgeCandidate) -> str:
    """'promote' ou 'hold' segundo os eixos confidence × risk."""
    if not governance_enabled():
        return "promote"
    if candidate.risk == "high":
        return "hold"
    if candidate.confidence == "hypothesis":
        return "hold"
    return "promote"


def ensure_knowledge_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge_candidates (
            id TEXT PRIMARY KEY,
            source_type TEXT NOT NULL,
            source_id TEXT NOT NULL,
            knowledge_type TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            project TEXT NOT NULL DEFAULT 'default',
            workspace_id TEXT NOT NULL DEFAULT 'default',
            evidence_json TEXT NOT NULL,
            metadata_json TEXT,
            hash TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'candidate',
            neuron_id TEXT,
            error TEXT,
            retry_policy TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            promoted_at TEXT,
            UNIQUE(source_id, knowledge_type, hash, workspace_id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_knowledge_candidates_source
        ON knowledge_candidates(source_type, source_id, status)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_knowledge_candidates_type_workspace
        ON knowledge_candidates(knowledge_type, workspace_id, status)
        """
    )
    add_column_if_missing(conn, "knowledge_candidates", "confidence TEXT NOT NULL DEFAULT 'verified'")
    add_column_if_missing(conn, "knowledge_candidates", "risk TEXT NOT NULL DEFAULT 'low'")
    add_column_if_missing(conn, "knowledge_candidates", "ttl_review TEXT")
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_knowledge_candidates_held
        ON knowledge_candidates(status, risk)
        """
    )


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data or {}, ensure_ascii=False, sort_keys=True)


def _candidate_row(candidate: KnowledgeCandidate) -> tuple:
    return (
        candidate.id,
        candidate.source_type,
        candidate.source_id,
        candidate.knowledge_type,
        candidate.title,
        candidate.content,
        candidate.project,
        candidate.workspace_id,
        _json(candidate.evidence),
        _json(candidate.metadata),
        candidate.hash,
        candidate.created_at,
        candidate.confidence,
        candidate.risk,
    )


def store_candidates(conn, candidates: Iterable[KnowledgeCandidate]) -> int:
    ensure_knowledge_schema(conn)
    count = 0
    for candidate in candidates:
        conn.execute(
            """
            INSERT INTO knowledge_candidates(
                id, source_type, source_id, knowledge_type, title, content,
                project, workspace_id, evidence_json, metadata_json, hash,
                created_at, confidence, risk
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title,
                content=excluded.content,
                project=excluded.project,
                workspace_id=excluded.workspace_id,
                evidence_json=excluded.evidence_json,
                metadata_json=excluded.metadata_json,
                hash=excluded.hash,
                confidence=excluded.confidence,
                risk=excluded.risk
            """,
            _candidate_row(candidate),
        )
        count += 1
    return count


def _neuron_id(candidate: KnowledgeCandidate) -> str:
    return f"k3-{candidate.knowledge_type}-{candidate.hash[:16]}"


def _ttl_review(candidate: KnowledgeCandidate) -> str:
    try:
        base = datetime.fromisoformat(candidate.created_at.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        base = datetime.now(timezone.utc)
    return (base + timedelta(days=TTL_REVIEW_DAYS)).isoformat()


def _candidate_metadata(candidate: KnowledgeCandidate) -> dict[str, Any]:
    return {
        "source": "knowledge_promotion",
        "candidate_id": candidate.id,
        "source_type": candidate.source_type,
        "source_id": candidate.source_id,
        "source_observation_id": candidate.source_id if candidate.source_type != "file" else None,
        "evidence": candidate.evidence,
        "candidate_metadata": candidate.metadata,
        "governance": {
            "confidence": candidate.confidence,
            "risk": candidate.risk,
            "ttl_review": _ttl_review(candidate),
        },
    }


def _promote_to_neuron(conn, candidate: KnowledgeCandidate) -> str:
    neuron_id = _neuron_id(candidate)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO neurons(
            id, label, type, content, hash, metadata, created_at, updated_at,
            workspace_id, embedding_model, embedding_dim
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            label=excluded.label,
            type=excluded.type,
            content=excluded.content,
            hash=excluded.hash,
            metadata=excluded.metadata,
            updated_at=excluded.updated_at,
            workspace_id=excluded.workspace_id,
            embedding_model=excluded.embedding_model,
            embedding_dim=excluded.embedding_dim
        """,
        (
            neuron_id,
            candidate.title,
            candidate.knowledge_type,
            candidate.content,
            candidate.hash,
            _json(_candidate_metadata(candidate)),
            candidate.created_at,
            now,
            candidate.workspace_id,
            "snowflake-arctic-embed2:latest",
            1024,
        ),
    )
    return neuron_id


def _promote_next_step(conn, candidate: KnowledgeCandidate) -> str:
    goal_id = f"goal-{candidate.hash[:16]}"
    conn.execute(
        """
        INSERT INTO goals(id, description, steps_json, status, created_at, workspace_id)
        VALUES (?, ?, ?, 'active', ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            description=excluded.description,
            steps_json=excluded.steps_json,
            status=goals.status,
            workspace_id=excluded.workspace_id
        """,
        (
            goal_id,
            candidate.content,
            json.dumps([candidate.content], ensure_ascii=False),
            candidate.created_at,
            candidate.workspace_id,
        ),
    )
    return goal_id


def promote_candidate(conn, candidate: KnowledgeCandidate) -> str | None:
    ensure_knowledge_schema(conn)
    if candidate.knowledge_type == "next_step":
        goal_id = _promote_next_step(conn, candidate)
        conn.execute(
            """
            UPDATE knowledge_candidates
            SET status='promoted', promoted_at=?, ttl_review=?, neuron_id=NULL,
                error=NULL, retry_policy=NULL
            WHERE id=?
            """,
            (datetime.now(timezone.utc).isoformat(), _ttl_review(candidate), candidate.id),
        )
        return None
    neuron_id = _promote_to_neuron(conn, candidate)
    conn.execute(
        """
        UPDATE knowledge_candidates
        SET status='promoted', promoted_at=?, ttl_review=?, neuron_id=?,
            error=NULL, retry_policy=NULL
        WHERE id=?
        """,
        (datetime.now(timezone.utc).isoformat(), _ttl_review(candidate), neuron_id, candidate.id),
    )
    return neuron_id


def hold_candidate(conn, candidate: KnowledgeCandidate, *, reason: str) -> None:
    """Segura o candidato na fila de revisão (status='held').

    O raw em `observations` segue intocado; o candidato tipado É a fila de
    revisão — `promote_held_candidates` (drenagem periódica) decide depois.
    """
    ensure_knowledge_schema(conn)
    conn.execute(
        """
        UPDATE knowledge_candidates
        SET status='held', error=?, retry_policy='governance_review'
        WHERE id=? AND status != 'promoted'
        """,
        (reason, candidate.id),
    )


def _metadata_dict(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    try:
        parsed = json.loads(str(raw))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def quarantine_observation(conn, obs_id: str, reason: str, *, retry_policy: str = "manual_fix_required") -> None:
    row = conn.execute("SELECT metadata FROM observations WHERE id = ?", (obs_id,)).fetchone()
    metadata = _metadata_dict(row["metadata"] if row else None)
    metadata["quarantine"] = {
        "reason": reason,
        "retry_policy": retry_policy,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    conn.execute(
        "UPDATE observations SET archived = 2, metadata = ? WHERE id = ?",
        (_json(metadata), obs_id),
    )


def _pending_rows(conn, *, limit: int | None = None):
    sql = """
    SELECT *
    FROM observations
    WHERE COALESCE(archived, 0) = 0
    ORDER BY created_at, id
    """
    params: tuple[Any, ...] = ()
    if limit is not None:
        sql += " LIMIT ?"
        params = (int(limit),)
    return conn.execute(sql, params).fetchall()


def promote_pending_observations(conn, *, limit: int | None = None, apply: bool = True) -> dict[str, int]:
    """Normaliza e promove observations pendentes com governança por risco.

    `apply=False` executa a classificacao sem escrever. O raw em `observations`
    nunca e alterado exceto pelos marcadores operacionais `archived`,
    `neuron_id` e metadados de quarentena.

    Cada candidato passa por `_governance_action`: verified+low promove na
    hora; hypothesis ou risk=high fica `held` na fila de revisão (a
    observation é marcada archived=1 mesmo assim — o candidato tipado carrega
    a pendência, drenada por `promote_held_candidates`).
    """
    ensure_knowledge_schema(conn)
    rows = _pending_rows(conn, limit=limit)
    report = {
        "observations": len(rows),
        "candidates": 0,
        "promoted": 0,
        "held_hypothesis": 0,
        "held_high_risk": 0,
        "quarantined": 0,
        "skipped": 0,
    }
    if not apply:
        for row in rows:
            try:
                report["candidates"] += len(normalize_observation(row))
            except StructuralIntakeError:
                report["quarantined"] += 1
        return report

    for row in rows:
        obs_id = str(row["id"])
        try:
            candidates = normalize_observation(row)
            report["candidates"] += store_candidates(conn, candidates)
            first_neuron_id: str | None = None
            for candidate in candidates:
                if _governance_action(candidate) == "hold":
                    if candidate.risk == "high":
                        hold_candidate(conn, candidate, reason="risk=high aguardando revisão")
                        report["held_high_risk"] += 1
                    else:
                        hold_candidate(conn, candidate, reason="confidence=hypothesis aguardando drenagem")
                        report["held_hypothesis"] += 1
                    continue
                neuron_id = promote_candidate(conn, candidate)
                report["promoted"] += 1
                if neuron_id:
                    first_neuron_id = first_neuron_id or neuron_id
            if first_neuron_id:
                conn.execute(
                    "UPDATE observations SET neuron_id = ? WHERE id = ? AND neuron_id IS NULL",
                    (first_neuron_id, obs_id),
                )
            conn.execute("UPDATE observations SET archived = 1 WHERE id = ?", (obs_id,))
        except StructuralIntakeError as exc:
            quarantine_observation(conn, obs_id, str(exc))
            report["quarantined"] += 1
        except Exception as exc:
            quarantine_observation(conn, obs_id, f"erro estrutural na promoção: {type(exc).__name__}: {exc}")
            report["quarantined"] += 1
    conn.commit()
    return report


def _row_to_candidate(row: Any) -> KnowledgeCandidate:
    """Reconstrói um KnowledgeCandidate a partir da linha persistida."""
    return KnowledgeCandidate(
        id=str(row["id"]),
        source_type=str(row["source_type"]),
        source_id=str(row["source_id"]),
        knowledge_type=str(row["knowledge_type"]),
        title=str(row["title"]),
        content=str(row["content"]),
        project=str(row["project"] or "default"),
        workspace_id=str(row["workspace_id"] or "default"),
        evidence=_metadata_dict(row["evidence_json"]),
        metadata=_metadata_dict(row["metadata_json"]),
        hash=str(row["hash"]),
        created_at=str(row["created_at"] or ""),
        confidence=str(row["confidence"] or "hypothesis"),
        risk=str(row["risk"] or "low"),
    )


def promote_held_candidates(
    conn,
    *,
    min_age_days: int = HELD_MIN_AGE_DAYS,
    include_high_risk: bool = False,
    apply: bool = True,
    limit: int | None = None,
) -> dict[str, Any]:
    """Drena a fila de revisão (status='held').

    hypothesis+low promove após `min_age_days` (janela para o humano vetar via
    revisão do relatório). risk=high só promove com `include_high_risk=True` —
    aprovação explícita, nunca automática.
    """
    ensure_knowledge_schema(conn)
    sql = "SELECT * FROM knowledge_candidates WHERE status='held' ORDER BY created_at, id"
    params: tuple[Any, ...] = ()
    if limit is not None:
        sql += " LIMIT ?"
        params = (int(limit),)
    rows = conn.execute(sql, params).fetchall()
    now = datetime.now(timezone.utc)
    report: dict[str, Any] = {
        "held": len(rows),
        "promoted": 0,
        "skipped_recent": 0,
        "skipped_high_risk": 0,
        "errors": 0,
        "dry_run": not apply,
    }
    for row in rows:
        risk = str(row["risk"] or "low")
        if risk == "high" and not include_high_risk:
            report["skipped_high_risk"] += 1
            continue
        if risk != "high":
            try:
                created = datetime.fromisoformat(str(row["created_at"]).replace("Z", "+00:00"))
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                created = now
            if (now - created).days < min_age_days:
                report["skipped_recent"] += 1
                continue
        if not apply:
            report["promoted"] += 1
            continue
        try:
            promote_candidate(conn, _row_to_candidate(row))
            report["promoted"] += 1
        except Exception as exc:
            report["errors"] += 1
            conn.execute(
                "UPDATE knowledge_candidates SET error=? WHERE id=?",
                (f"held drain failed: {type(exc).__name__}: {exc}", str(row["id"])),
            )
    if apply:
        conn.commit()
    return report


def held_review_queue(conn) -> dict[str, int]:
    """Contagem da fila de revisão por risco, para knowledge_health/relatórios."""
    ensure_knowledge_schema(conn)
    counts = {"held_total": 0, "held_high_risk": 0, "held_hypothesis": 0}
    for row in conn.execute(
        "SELECT risk, COUNT(*) AS n FROM knowledge_candidates WHERE status='held' GROUP BY risk"
    ).fetchall():
        n = int(row["n"])
        counts["held_total"] += n
        if str(row["risk"]) == "high":
            counts["held_high_risk"] += n
        else:
            counts["held_hypothesis"] += n
    return counts


def promote_files(
    conn,
    paths: Iterable[str | Path],
    *,
    project: str = "default",
    workspace_id: str = "default",
    apply: bool = True,
) -> dict[str, int]:
    """Normaliza/promove arquivos, codigo e summaries sem observation raw.

    Arquivos vazios/ausentes entram como quarentena operacional no relatório
    (`quarantined`), mas não criam linha em observations porque a fonte primária
    é o próprio path em `evidence.source_uri`.
    """
    ensure_knowledge_schema(conn)
    report = {"files": 0, "candidates": 0, "promoted": 0, "quarantined": 0}
    for raw_path in paths:
        report["files"] += 1
        try:
            candidate = normalize_markdown_file(
                Path(raw_path), project=project, workspace_id=workspace_id
            )
            if not apply:
                report["candidates"] += 1
                continue
            report["candidates"] += store_candidates(conn, [candidate])
            promote_candidate(conn, candidate)
            report["promoted"] += 1
        except (OSError, StructuralIntakeError):
            report["quarantined"] += 1
    if apply:
        conn.commit()
    return report


__all__ = [
    "ensure_knowledge_schema",
    "governance_enabled",
    "held_review_queue",
    "hold_candidate",
    "promote_files",
    "promote_candidate",
    "promote_held_candidates",
    "promote_pending_observations",
    "quarantine_observation",
    "store_candidates",
]
