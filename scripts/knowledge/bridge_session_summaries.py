#!/usr/bin/env python3
"""Bridge: importa session_summaries do claude-mem para cerebelo/sessoes/.

F2.2a (2026-08-13): a cadeia da cadência (sessoes→diario→semanal→mensal→anual)
estava quebrada no PRIMEIRO elo — o claude-mem acumula 5.423 session_summaries
(ricos: request/investigated/learned/completed/next_steps), mas o
session_consolidator.py lê cerebelo/sessoes/YYYY/MM/DD/ e NINGUÉM materializava
esses summaries lá. Este bridge transpõe cada session_summary do claude-mem para
um session log `.md` no vault, no formato que o daily_writer espera.

Determinístico (sem LLM): o summary já está estruturado pelo claude-mem; aqui só
reorganizamos em markdown. Idempotente por `origin_local_id`/`memory_session_id`
(arquivo nomeado por id, nunca duplica).

Uso:
    python scripts/knowledge/bridge_session_summaries.py --dry-run   # conta
    python scripts/knowledge/bridge_session_summaries.py --apply     # importa
    python scripts/knowledge/bridge_session_summaries.py --apply --limit 100
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
ROOT = _HERE.parent.parent
sys.path.insert(0, str(ROOT))

from core import paths as cp  # noqa: E402


def _claude_mem_db() -> Path:
    return Path(os.environ.get(
        "CLAUDE_MEM_DB",
        str(ROOT / "claude-mem" / "data" / "claude-mem.db"),
    ))


def _session_date(created_at: str | None) -> datetime:
    """Converte created_at ISO (ex.: 2026-08-12T21:44:02.938Z) em datetime."""
    if not created_at:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


def _slug(text: str | None, max_len: int = 40) -> str:
    import re
    s = re.sub(r"[^a-z0-9]+", "-", (text or "session").lower()).strip("-")
    return s[:max_len].rstrip("-") or "session"


def _session_body(row: sqlite3.Row) -> str:
    """Renderiza um session_summary como session log .md canônico.

    Usa os campos que o daily_writer._session_label espera: `description`,
    `session_id` e `consolidated` (não `memory_session_id`).
    """
    dt = _session_date(row["created_at"])
    title = (row["request"] or "Session").strip()
    project = (row["project"] or "default").strip() or "default"
    sid = (row["memory_session_id"] or f"s-{row['id']}").strip()

    lines = [
        "---",
        "type: session-log",
        f"project: {project}",
        f"description: {title}",
        f"session_id: {sid}",
        "consolidated: false",
        f"date: {dt.strftime('%Y-%m-%d')}",
        f"created_at: {row['created_at'] or ''}",
        "source: claude-mem",
        "---",
        f"# {title}",
        "",
    ]
    for label, field in (
        ("Objetivo", "request"),
        ("Investigado", "investigated"),
        ("Aprendido", "learned"),
        ("Concluído", "completed"),
        ("Próximos passos", "next_steps"),
        ("Arquivos lidos", "files_read"),
        ("Arquivos editados", "files_edited"),
        ("Notas", "notes"),
    ):
        val = row[field]
        if val and str(val).strip() and str(val).strip().lower() != "none":
            lines.append(f"## {label}")
            lines.append(str(val).strip())
            lines.append("")

    lines.extend([
        "## Sinapses",
        f"- projeto:: [[{project}]]",
        "- lobo:: [[cerebelo]]",
    ])
    return "\n".join(lines) + "\n"


def bridge(limit: int | None = None, *, apply: bool = False) -> dict:
    db = _claude_mem_db()
    if not db.exists():
        return {"source_missing": True, "imported": 0}

    conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    sql = "SELECT * FROM session_summaries ORDER BY created_at_epoch ASC"
    if limit:
        sql += " LIMIT ?"
        rows = conn.execute(sql, (limit,)).fetchall()
    else:
        rows = conn.execute(sql).fetchall()
    conn.close()

    report = {"scanned": len(rows), "imported": 0, "skipped": 0, "failed": 0}
    for row in rows:
        dt = _session_date(row["created_at"])
        folder = cp.SESSIONS_ROOT / dt.strftime("%Y/%m/%d")
        mid = (row["memory_session_id"] or f"s-{row['id']}").split("-")[-1][:16]
        fname = f"{dt.strftime('%H%M')}-{_slug(row['request'])}-{mid}.md"
        dest = folder / fname

        if dest.exists():
            report["skipped"] += 1
            continue

        if not apply:
            report["imported"] += 1
            continue

        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(_session_body(row), encoding="utf-8")
            report["imported"] += 1
        except Exception:
            report["failed"] += 1

    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="Importa session_summaries do claude-mem para cerebelo/sessoes/")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    report = bridge(limit=args.limit, apply=args.apply)
    if report.get("source_missing"):
        print("claude-mem session_summaries não encontrado.")
        return 1
    print(f"scanned:  {report['scanned']}")
    print(f"imported: {report['imported']}")
    print(f"skipped:  {report['skipped']}")
    print(f"failed:   {report['failed']}")
    if not args.apply:
        print("[dry-run] use --apply para escrever")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
