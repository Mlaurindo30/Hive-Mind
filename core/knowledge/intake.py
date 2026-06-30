"""K3 Knowledge Intake.

Normaliza entradas brutas (observations, discoveries, summaries e arquivos)
em candidatos tipados. Esta camada nao escreve no vault nem no banco: ela
classifica, preserva evidencia e deixa `promotion.py` decidir persistencia.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any


CANONICAL_TYPES = {
    "fact",
    "decision",
    "learning",
    "preference",
    "rationale",
    "next_step",
    "operational_fact",
    "project_status",
    "document_chunk",
    "code_symbol",
    "visual_observation",
}


class StructuralIntakeError(ValueError):
    """Input sem estrutura minima para virar candidato de conhecimento."""


@dataclass(frozen=True)
class KnowledgeCandidate:
    id: str
    source_type: str
    source_id: str
    knowledge_type: str
    title: str
    content: str
    project: str = "default"
    workspace_id: str = "default"
    evidence: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    hash: str = ""
    created_at: str = ""

    def __post_init__(self) -> None:
        if self.knowledge_type not in CANONICAL_TYPES:
            raise ValueError(f"tipo canonico desconhecido: {self.knowledge_type}")
        if not self.title.strip() or not self.content.strip():
            raise StructuralIntakeError("candidato sem título ou sem conteúdo")


def _json_loads(value: Any) -> Any:
    if value is None or value == "":
        return {}
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except Exception:
        return {}


def _row_value(row: Any, key: str, default: Any = None) -> Any:
    if isinstance(row, sqlite3.Row):
        return row[key] if key in row.keys() else default
    if isinstance(row, dict):
        return row.get(key, default)
    return getattr(row, key, default)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        if not value.strip():
            return []
        parsed = _json_loads(value)
        if isinstance(parsed, list):
            return parsed
        return [value]
    return [value]


def _text_of(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("text", "content", "title", "summary", "description", "value"):
            if value.get(key):
                return str(value[key]).strip()
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value or "").strip()


def _title_for(kind: str, text: str, fallback: str) -> str:
    first = text.splitlines()[0].strip() if text else ""
    if first:
        return first[:120]
    return fallback[:120] or kind.replace("_", " ").title()


def _stable_hash(*parts: str) -> str:
    payload = "\n".join(str(part or "") for part in parts)
    return hashlib.sha256(payload.encode("utf-8", "ignore")).hexdigest()


def _candidate(
    *,
    source_type: str,
    source_id: str,
    knowledge_type: str,
    title: str,
    content: str,
    project: str,
    workspace_id: str,
    evidence: dict[str, Any],
    metadata: dict[str, Any],
    created_at: str,
) -> KnowledgeCandidate:
    digest = _stable_hash(workspace_id, source_type, source_id, knowledge_type, title, content)
    return KnowledgeCandidate(
        id=f"kc-{digest[:24]}",
        source_type=source_type,
        source_id=source_id,
        knowledge_type=knowledge_type,
        title=title,
        content=content,
        project=project or "default",
        workspace_id=workspace_id or "default",
        evidence=evidence,
        metadata=metadata,
        hash=digest,
        created_at=created_at or datetime.now(timezone.utc).isoformat(),
    )


def build_candidate(
    *,
    source_type: str,
    source_id: str,
    knowledge_type: str,
    title: str,
    content: str,
    project: str = "default",
    workspace_id: str = "default",
    evidence: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    created_at: str | None = None,
) -> KnowledgeCandidate:
    """Construtor público para promotores especializados gerarem candidatos."""
    return _candidate(
        source_type=source_type,
        source_id=source_id,
        knowledge_type=knowledge_type,
        title=title,
        content=content,
        project=project,
        workspace_id=workspace_id,
        evidence=evidence or {},
        metadata=metadata or {},
        created_at=created_at or datetime.now(timezone.utc).isoformat(),
    )


def _payload_from_observation(row: Any, metadata: dict[str, Any]) -> dict[str, Any]:
    content = str(_row_value(row, "content", "") or "").strip()
    payload = _json_loads(content)
    if isinstance(payload, dict):
        merged = dict(payload)
        for key, value in metadata.items():
            merged.setdefault(key, value)
        return merged
    return dict(metadata)


def _evidence(row: Any, metadata: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    evidence = payload.get("evidence") or metadata.get("evidence") or {}
    if not isinstance(evidence, dict):
        evidence = {"items": _as_list(evidence)}
    evidence.setdefault("source_observation_id", str(_row_value(row, "id", "")))
    evidence.setdefault("source_title", str(_row_value(row, "title", "") or ""))
    files = payload.get("files_read") or payload.get("files_modified") or metadata.get("files")
    if files and "files" not in evidence:
        evidence["files"] = _as_list(files)
    return evidence


def normalize_observation(row: Any) -> list[KnowledgeCandidate]:
    """Transforma uma observation do UMC em candidatos canônicos.

    Suporta observations vindas do claude-mem bridge, discoveries enriquecidos,
    session summaries, documentos/codigo/visao e eventos simples. Em erro
    estrutural levanta `StructuralIntakeError`; quem chama decide quarentena.
    """
    source_id = str(_row_value(row, "id", "") or "")
    if not source_id:
        raise StructuralIntakeError("observação sem id")

    metadata = _json_loads(_row_value(row, "metadata"))
    if not isinstance(metadata, dict):
        metadata = {}
    payload = _payload_from_observation(row, metadata)
    title = str(_row_value(row, "title", "") or payload.get("title") or "").strip()
    content = str(_row_value(row, "content", "") or payload.get("text") or payload.get("narrative") or "").strip()
    obs_type = str(_row_value(row, "type", "") or payload.get("type") or "event").strip().lower()
    source_type = str(payload.get("source_kind") or metadata.get("source_kind") or obs_type or "observation")
    project = str(_row_value(row, "project", "") or payload.get("project") or metadata.get("project") or "default")
    workspace_id = str(_row_value(row, "workspace_id", "") or metadata.get("workspace_id") or "default")
    created_at = str(_row_value(row, "created_at", "") or datetime.now(timezone.utc).isoformat())
    evidence = _evidence(row, metadata, payload)
    concepts = payload.get("concepts") or metadata.get("concepts") or []

    common_meta = {
        "observation_type": obs_type,
        "source_kind": source_type,
        "concepts": _as_list(concepts),
    }

    candidates: list[KnowledgeCandidate] = []

    def add_many(field: str, knowledge_type: str, fallback_title: str) -> None:
        for item in _as_list(payload.get(field) or metadata.get(field)):
            text = _text_of(item)
            if not text:
                continue
            candidates.append(_candidate(
                source_type=source_type,
                source_id=source_id,
                knowledge_type=knowledge_type,
                title=_title_for(knowledge_type, text, fallback_title),
                content=text,
                project=project,
                workspace_id=workspace_id,
                evidence=evidence,
                metadata={**common_meta, "field": field},
                created_at=created_at,
            ))

    add_many("facts", "fact", title)
    add_many("decisions", "decision", title)
    add_many("decision", "decision", title)
    add_many("learned", "learning", title)
    add_many("learnings", "learning", title)
    add_many("preferences", "preference", title)
    add_many("next_steps", "next_step", title)
    add_many("completed", "operational_fact", title)

    narrative = payload.get("narrative") or payload.get("investigated") or metadata.get("narrative")
    if narrative:
        text = _text_of(narrative)
        candidates.append(_candidate(
            source_type=source_type,
            source_id=source_id,
            knowledge_type="rationale",
            title=_title_for("rationale", text, title or "Investigação"),
            content=text,
            project=project,
            workspace_id=workspace_id,
            evidence=evidence,
            metadata={**common_meta, "field": "narrative"},
            created_at=created_at,
        ))

    direct_type_map = {
        "fact": "fact",
        "decision": "decision",
        "learning": "learning",
        "preference": "preference",
        "rationale": "rationale",
        "next_step": "next_step",
        "operational_fact": "operational_fact",
        "project_status": "project_status",
        "document": "document_chunk",
        "document_chunk": "document_chunk",
        "code": "code_symbol",
        "code_symbol": "code_symbol",
        "visual": "visual_observation",
        "visual_observation": "visual_observation",
        "session_summary": "project_status",
        "summary": "project_status",
        "change": "operational_fact",
    }
    if not candidates and obs_type in direct_type_map and content:
        candidates.append(_candidate(
            source_type=source_type,
            source_id=source_id,
            knowledge_type=direct_type_map[obs_type],
            title=title or _title_for(obs_type, content, obs_type),
            content=content,
            project=project,
            workspace_id=workspace_id,
            evidence=evidence,
            metadata={**common_meta, "field": "content"},
            created_at=created_at,
        ))

    if not candidates and content and obs_type in {"event", "discovery", "observation"}:
        candidates.append(_candidate(
            source_type=source_type,
            source_id=source_id,
            knowledge_type="fact",
            title=title or _title_for("fact", content, "Observação"),
            content=content,
            project=project,
            workspace_id=workspace_id,
            evidence=evidence,
            metadata={**common_meta, "field": "content"},
            created_at=created_at,
        ))

    if not candidates:
        raise StructuralIntakeError("observação sem conteúdo promovível")
    return candidates


def _file_knowledge_type(path: Path) -> tuple[str, dict[str, Any]]:
    suffix = path.suffix.lower()
    parts = {part.lower() for part in path.parts}
    cadence_map = {
        "sessoes": "session",
        "sessions": "session",
        "diario": "daily",
        "daily": "daily",
        "semanal": "weekly",
        "weekly": "weekly",
        "mensal": "monthly",
        "monthly": "monthly",
        "anual": "yearly",
        "yearly": "yearly",
    }
    for marker, cadence in cadence_map.items():
        if marker in parts:
            return "project_status", {"cadence": cadence}
    if suffix in {".py", ".js", ".ts", ".tsx", ".go", ".rs", ".java"}:
        return "code_symbol", {}
    return "document_chunk", {}


def normalize_markdown_file(path: Path, *, project: str = "default", workspace_id: str = "default") -> KnowledgeCandidate:
    text = path.read_text(encoding="utf-8", errors="ignore").strip()
    if not text:
        raise StructuralIntakeError(f"arquivo sem conteúdo: {path}")
    source_id = str(path)
    knowledge_type, file_metadata = _file_knowledge_type(path)
    return _candidate(
        source_type="file",
        source_id=source_id,
        knowledge_type=knowledge_type,
        title=path.name,
        content=text[:5000],
        project=project,
        workspace_id=workspace_id,
        evidence={"source_uri": source_id},
        metadata={"field": "file", **file_metadata},
        created_at=datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
    )
