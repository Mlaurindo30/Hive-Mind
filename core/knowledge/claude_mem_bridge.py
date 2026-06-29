"""Claude-Mem -> Hive-Mind bridge (K4).

The bridge intentionally reads the local/global ``claude-mem.db`` by SQL in
read-only mode. That is the robust path for promotion/backfill because it can
scan by table, source id and temporal window without depending on temporal MCP
search wording.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import sqlite3
from typing import Any, Iterable, Optional

from core.database import ensure_migrations, get_connection


logger = logging.getLogger("claude_mem_bridge")

CLAUDE_MEM_DB = Path(os.environ.get("CLAUDE_MEM_DB", str(Path.home() / ".claude-mem" / "claude-mem.db")))
DEFAULT_LIMIT = 1000
BRIDGE_SOURCE = "claude-mem-bridge"
SOURCE_TABLES = ("observations", "discoveries", "session_summaries")


@dataclass(frozen=True)
class SourceRecord:
    table: str
    source_id: str
    observation_id: str
    project: str
    obs_type: str
    title: str
    content: str
    created_at: str
    created_at_epoch: int | None
    metadata: dict[str, Any]


def _json_loads(value: Any) -> Any:
    if value is None or value == "":
        return {}
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except Exception:
        return value


def _as_json_value(value: Any) -> Any:
    parsed = _json_loads(value)
    return parsed


def _as_list(value: Any) -> list[Any]:
    parsed = _json_loads(value)
    if parsed is None or parsed == "":
        return []
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, tuple):
        return list(parsed)
    return [parsed]


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _content_hash(*parts: Any) -> str:
    payload = "|".join(str(part or "") for part in parts)
    return hashlib.sha256(payload.encode("utf-8", "ignore")).hexdigest()[:24]


def _source_id(table: str, source_pk: Any) -> str:
    return f"claude-mem:{table}:{source_pk}"


def _observation_id(table: str, row: dict[str, Any], payload: dict[str, Any]) -> str:
    if table == "observations":
        h = row.get("content_hash")
        if h:
            return f"cm-{h}"
    h = row.get("content_hash") or _content_hash(table, row.get("id"), payload)
    return f"cm-{table}-{h}"


def open_claude_mem(db_path: Path = CLAUDE_MEM_DB) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _parse_source_ids(source_ids: Iterable[str] | None) -> dict[str, set[str]]:
    parsed: dict[str, set[str]] = {}
    for raw in source_ids or []:
        value = str(raw).strip()
        if not value:
            continue
        if value.startswith("claude-mem:"):
            parts = value.split(":", 2)
            if len(parts) == 3:
                table, pk = parts[1], parts[2]
                parsed.setdefault(table, set()).add(pk)
                continue
        if ":" in value:
            table, pk = value.split(":", 1)
            parsed.setdefault(table, set()).add(pk)
            continue
        for table in SOURCE_TABLES:
            parsed.setdefault(table, set()).add(value)
    return parsed


def _select_rows(
    conn: sqlite3.Connection,
    table: str,
    *,
    source_ids: dict[str, set[str]] | None = None,
    since_epoch: int | None = None,
    until_epoch: int | None = None,
    limit: int | None = None,
) -> list[sqlite3.Row]:
    if not _table_exists(conn, table):
        return []
    cols = _columns(conn, table)
    where: list[str] = []
    params: list[Any] = []
    ids = (source_ids or {}).get(table)
    if ids:
        placeholders = ",".join("?" for _ in ids)
        where.append(f"id IN ({placeholders})")
        params.extend(sorted(ids, key=str))
    if since_epoch is not None and "created_at_epoch" in cols:
        where.append("created_at_epoch >= ?")
        params.append(int(since_epoch))
    if until_epoch is not None and "created_at_epoch" in cols:
        where.append("created_at_epoch <= ?")
        params.append(int(until_epoch))
    sql = f"SELECT * FROM {table}"
    if where:
        sql += " WHERE " + " AND ".join(where)
    order_col = "created_at_epoch" if "created_at_epoch" in cols else "id"
    sql += f" ORDER BY {order_col} ASC"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(int(limit))
    return conn.execute(sql, params).fetchall()


def _common_metadata(table: str, row: dict[str, Any], source_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    meta = _json_loads(row.get("metadata"))
    if not isinstance(meta, dict):
        meta = {}
    files = []
    for key in ("files_read", "files_modified", "files_edited"):
        files.extend(_as_list(row.get(key)))
    return {
        **meta,
        "source": BRIDGE_SOURCE,
        "source_kind": payload.get("source_kind") or ("session_summary" if table == "session_summaries" else "discovery"),
        "source_id": source_id,
        "source_table": table,
        "cm_id": row.get("id"),
        "cm_epoch": row.get("created_at_epoch"),
        "memory_session_id": row.get("memory_session_id"),
        "prompt_number": row.get("prompt_number"),
        "project": row.get("project"),
        "evidence": {
            "source_id": source_id,
            "source_table": table,
            "files": files,
            "created_at": row.get("created_at"),
        },
    }


def _record_from_observation(row: sqlite3.Row) -> SourceRecord | None:
    raw = _row_dict(row)
    payload: dict[str, Any] = {
        "source_kind": raw.get("type") or "observation",
        "type": raw.get("type") or "event",
        "text": raw.get("text"),
        "title": raw.get("title"),
        "facts": _as_json_value(raw.get("facts")),
        "narrative": raw.get("narrative"),
        "concepts": _as_json_value(raw.get("concepts")),
        "files_read": _as_json_value(raw.get("files_read")),
        "files_modified": _as_json_value(raw.get("files_modified")),
    }
    content_text = str(raw.get("text") or raw.get("narrative") or "").strip()
    has_structured = any(payload.get(key) for key in ("facts", "narrative", "concepts", "files_read", "files_modified"))
    if not content_text and not has_structured:
        return None
    if not has_structured:
        content = content_text
    else:
        payload["content"] = content_text
        content = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    sid = _source_id("observations", raw.get("id"))
    metadata = _common_metadata("observations", raw, sid, payload)
    return SourceRecord(
        table="observations",
        source_id=sid,
        observation_id=_observation_id("observations", raw, payload),
        project=str(raw.get("project") or "Hive-Mind"),
        obs_type=str(raw.get("type") or "event"),
        title=str(raw.get("title") or "(sem titulo)"),
        content=content,
        created_at=str(raw.get("created_at") or datetime.now(timezone.utc).isoformat()),
        created_at_epoch=raw.get("created_at_epoch"),
        metadata=metadata,
    )


def _record_from_discovery(row: sqlite3.Row) -> SourceRecord | None:
    raw = _row_dict(row)
    payload = {
        "source_kind": "discovery",
        "type": "discovery",
        "title": raw.get("title"),
        "facts": _as_json_value(raw.get("facts")),
        "narrative": raw.get("narrative"),
        "learned": _as_json_value(raw.get("learned")),
        "decisions": _as_json_value(raw.get("decisions")),
        "next_steps": _as_json_value(raw.get("next_steps")),
        "files_read": _as_json_value(raw.get("files_read")),
    }
    if not any(payload.get(key) for key in ("facts", "narrative", "learned", "decisions", "next_steps")):
        return None
    sid = _source_id("discoveries", raw.get("id"))
    metadata = _common_metadata("discoveries", raw, sid, payload)
    return SourceRecord(
        table="discoveries",
        source_id=sid,
        observation_id=_observation_id("discoveries", raw, payload),
        project=str(raw.get("project") or "Hive-Mind"),
        obs_type="discovery",
        title=str(raw.get("title") or "Claude-Mem discovery"),
        content=json.dumps(payload, ensure_ascii=False, sort_keys=True),
        created_at=str(raw.get("created_at") or datetime.now(timezone.utc).isoformat()),
        created_at_epoch=raw.get("created_at_epoch"),
        metadata=metadata,
    )


def _record_from_session_summary(row: sqlite3.Row) -> SourceRecord | None:
    raw = _row_dict(row)
    payload = {
        "source_kind": "session_summary",
        "type": "session_summary",
        "title": raw.get("request") or "Claude-Mem session summary",
        "request": raw.get("request"),
        "investigated": raw.get("investigated"),
        "learned": _as_json_value(raw.get("learned")),
        "completed": _as_json_value(raw.get("completed")),
        "decisions": _as_json_value(raw.get("decisions")),
        "next_steps": _as_json_value(raw.get("next_steps")),
        "notes": raw.get("notes"),
        "files_read": _as_json_value(raw.get("files_read")),
        "files_edited": _as_json_value(raw.get("files_edited")),
    }
    if not any(payload.get(key) for key in ("investigated", "learned", "completed", "decisions", "next_steps", "notes")):
        return None
    sid = _source_id("session_summaries", raw.get("id"))
    metadata = _common_metadata("session_summaries", raw, sid, payload)
    return SourceRecord(
        table="session_summaries",
        source_id=sid,
        observation_id=_observation_id("session_summaries", raw, payload),
        project=str(raw.get("project") or "Hive-Mind"),
        obs_type="session_summary",
        title=str(raw.get("request") or "Claude-Mem session summary")[:240],
        content=json.dumps(payload, ensure_ascii=False, sort_keys=True),
        created_at=str(raw.get("created_at") or datetime.now(timezone.utc).isoformat()),
        created_at_epoch=raw.get("created_at_epoch"),
        metadata=metadata,
    )


def _records_from_rows(table: str, rows: Iterable[sqlite3.Row]) -> list[SourceRecord]:
    builder = {
        "observations": _record_from_observation,
        "discoveries": _record_from_discovery,
        "session_summaries": _record_from_session_summary,
    }[table]
    records: list[SourceRecord] = []
    for row in rows:
        record = builder(row)
        if record is not None:
            records.append(record)
    return records


def fetch_source_records(
    cm_conn: sqlite3.Connection,
    *,
    limit: int | None = None,
    source_ids: Iterable[str] | None = None,
    since_epoch: int | None = None,
    until_epoch: int | None = None,
    tables: Iterable[str] = SOURCE_TABLES,
) -> list[SourceRecord]:
    parsed_ids = _parse_source_ids(source_ids)
    records: list[SourceRecord] = []
    remaining = limit
    for table in tables:
        if remaining is not None and remaining <= 0:
            break
        if parsed_ids and table not in parsed_ids:
            continue
        rows = _select_rows(
            cm_conn,
            table,
            source_ids=parsed_ids,
            since_epoch=since_epoch,
            until_epoch=until_epoch,
            limit=remaining,
        )
        built = _records_from_rows(table, rows)
        records.extend(built)
        if remaining is not None:
            remaining -= len(rows)
    records.sort(key=lambda rec: (rec.created_at_epoch if rec.created_at_epoch is not None else 0, rec.source_id))
    return records[:limit] if limit is not None else records


def existing_bridged_ids(hm_conn: sqlite3.Connection) -> set[str]:
    return {str(r[0]) for r in hm_conn.execute("SELECT id FROM observations WHERE id LIKE 'cm-%'")}


def _hm_observation_columns(hm_conn: sqlite3.Connection) -> set[str]:
    return {row[1] for row in hm_conn.execute("PRAGMA table_info(observations)").fetchall()}


def _insert_observation(hm_conn: sqlite3.Connection, rec: SourceRecord, project: str, metadata: dict[str, Any]) -> None:
    columns = _hm_observation_columns(hm_conn)
    base_cols = ["id", "project", "type", "title", "content", "created_at", "archived", "metadata"]
    values: list[Any] = [
        rec.observation_id,
        project,
        rec.obs_type,
        rec.title,
        rec.content,
        rec.created_at,
        0,
        json.dumps(metadata, ensure_ascii=False, sort_keys=True),
    ]
    if "workspace_id" in columns:
        base_cols.append("workspace_id")
        values.append(str(metadata.get("workspace_id") or "default"))
    placeholders = ", ".join("?" for _ in base_cols)
    hm_conn.execute(
        f"""
        INSERT OR IGNORE INTO observations({", ".join(base_cols)})
        VALUES ({placeholders})
        """,
        tuple(values),
    )


def bridge(
    *,
    cm_db: Path = CLAUDE_MEM_DB,
    limit: int = DEFAULT_LIMIT,
    dry_run: bool = False,
    default_project: str = "Hive-Mind",
    source_ids: Iterable[str] | None = None,
    since_epoch: int | None = None,
    until_epoch: int | None = None,
    tables: Iterable[str] = SOURCE_TABLES,
) -> dict[str, Any]:
    """Import claude-mem records into UMC observations.

    Direct SQL is kept deliberately: it avoids false negatives from long
    free-text temporal searches and supports deterministic backfill windows.
    """
    if not cm_db.exists():
        logger.warning("claude-mem.db not found at %s", cm_db)
        return {"scanned": 0, "inserted": 0, "skipped": 0, "by_source": {}}
    hm = get_connection()
    ensure_migrations(hm)
    cm = open_claude_mem(cm_db)
    try:
        already = existing_bridged_ids(hm)
        records = fetch_source_records(
            cm,
            limit=limit,
            source_ids=source_ids,
            since_epoch=since_epoch,
            until_epoch=until_epoch,
            tables=tables,
        )
        inserted = skipped = 0
        by_source: dict[str, int] = {}
        for rec in records:
            if rec.observation_id in already:
                skipped += 1
                continue
            project = rec.project.strip() or default_project
            metadata = dict(rec.metadata)
            metadata.setdefault("project", project)
            if not dry_run:
                _insert_observation(hm, rec, project, metadata)
            already.add(rec.observation_id)
            inserted += 1
            by_source[rec.table] = by_source.get(rec.table, 0) + 1
        if not dry_run:
            hm.commit()
        stats = {"scanned": len(records), "inserted": inserted, "skipped": skipped, "by_source": by_source}
        logger.info("claude_mem_bridge: %s", stats)
        return stats
    finally:
        cm.close()
        hm.close()


def quarantine_legacy(*, dry_run: bool = False) -> int:
    hm = get_connection()
    try:
        where = "project IS NULL AND id NOT LIKE 'cm-%' AND archived = 0"
        n = hm.execute(f"SELECT COUNT(*) FROM observations WHERE {where}").fetchone()[0]
        if not dry_run and n:
            hm.execute(f"UPDATE observations SET archived = 2 WHERE {where}")
            hm.commit()
        return int(n)
    finally:
        hm.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bridge claude-mem.db into hive_mind.db observations.")
    parser.add_argument("--dry-run", action="store_true", help="Count without writing")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--no-quarantine", action="store_true")
    parser.add_argument("--source-id", action="append", default=[], help="Filter source id, e.g. claude-mem:session_summaries:4055")
    parser.add_argument("--since-epoch", type=int)
    parser.add_argument("--until-epoch", type=int)
    parser.add_argument("--table", action="append", choices=SOURCE_TABLES, help="Restrict source table; repeatable")
    args = parser.parse_args(argv)

    print(json.dumps(
        bridge(
            limit=args.limit,
            dry_run=args.dry_run,
            source_ids=args.source_id,
            since_epoch=args.since_epoch,
            until_epoch=args.until_epoch,
            tables=args.table or SOURCE_TABLES,
        ),
        ensure_ascii=False,
        sort_keys=True,
    ))
    if not args.no_quarantine:
        quarantine_legacy(dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
