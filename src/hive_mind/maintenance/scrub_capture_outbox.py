from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from core.database import with_sqlite_retry
from core.redactor import redact_for_export
from hive_mind.maintenance.lock import MaintenanceLock
from scripts.utils.sanitizer import sanitize

_COMPACT_LIMIT = 500
_LEGACY_AUDIT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"HIVE_MIND_API_KEY\s*=\s*[^\s\\\"']*", re.IGNORECASE),
        "HIVE_MIND_API_KEY [REDACTED:token]",
    ),
    (
        re.compile(r"ANTHROPIC_API_KEY\s*=\s*[^\s\\\"']*", re.IGNORECASE),
        "ANTHROPIC_API_KEY [REDACTED:token]",
    ),
    (
        re.compile(r"OPENAI_API_KEY\s*=\s*[^\s\\\"']*", re.IGNORECASE),
        "OPENAI_API_KEY [REDACTED:token]",
    ),
    (
        re.compile(r"AIza[0-9A-Za-z_\-]{0,80}"),
        "[REDACTED:google-key]",
    ),
    (
        re.compile(r"sk-[A-Za-z0-9_\-]{2,80}"),
        "[REDACTED:token]",
    ),
]
_AUDIT_TRIGGER = re.compile(
    r"(?i)(Bearer\s+[A-Za-z0-9\-._~+/=]+|"
    r"HIVE_MIND_API_KEY\s*=|OPENAI_API_KEY\s*=|ANTHROPIC_API_KEY\s*=|"
    r"AIza[0-9A-Za-z_\-]{0,80}|sk-[A-Za-z0-9_\-]{8,80})"
)


@dataclass(frozen=True)
class OutboxSecretScrubReport:
    outbox_db: str
    apply: bool
    scanned_rows: int = 0
    changed_rows: int = 0
    changed_payload_rows: int = 0
    changed_error_rows: int = 0
    archive_rows: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _open_ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _open_rw(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 60000;")
    try:
        conn.execute("PRAGMA journal_mode = WAL;")
    except sqlite3.OperationalError:
        pass
    return conn


def _scrub_string(text: str) -> str:
    result = redact_for_export(sanitize(text))
    for pattern, replacement in _LEGACY_AUDIT_PATTERNS:
        result = pattern.sub(replacement, result)
    result = re.sub(r"Bearer\s+[A-Za-z0-9\-._~+/=]{6,}", "AUTHORIZATION [REDACTED:token]", result, flags=re.IGNORECASE)
    return result


def _compact_string(label: str, text: str) -> str:
    if len(text) <= _COMPACT_LIMIT and not _AUDIT_TRIGGER.search(text):
        return text
    digest = __import__("hashlib").sha256(text.encode("utf-8", errors="replace")).hexdigest()[:12]
    return f"[REDACTED:legacy-capture-{label} len={len(text)} sha256={digest}]"


def _compact_value(label: str, value: Any, *, depth: int = 0) -> Any:
    if depth > 20:
        return value
    if isinstance(value, str):
        return _compact_string(label, value)
    if isinstance(value, list):
        return [_compact_value(label, item, depth=depth + 1) for item in value]
    if isinstance(value, dict):
        compacted: dict[str, Any] = {}
        for key, item in value.items():
            child_label = str(key)
            compacted[key] = _compact_value(child_label, item, depth=depth + 1)
        return compacted
    return value


def _scrub_payload(payload: str) -> str:
    try:
        decoded = json.loads(payload)
    except Exception:
        return _compact_string("payload", _scrub_string(payload))
    cleaned = sanitize(decoded)
    compacted = _compact_value("payload", cleaned)
    return json.dumps(
        compacted,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _iter_rows(conn: sqlite3.Connection, table: str):
    return conn.execute(
        f"SELECT id, payload, COALESCE(last_error, '') AS last_error FROM {table}"
    )


def scrub_capture_outbox(*, outbox_db: str | Path, apply: bool = False) -> OutboxSecretScrubReport:
    path = Path(outbox_db)
    if not path.is_file():
        raise FileNotFoundError(path)

    ro = _open_ro(path)
    try:
        tables = {r[0] for r in ro.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "capture_outbox" not in tables:
            return OutboxSecretScrubReport(outbox_db=str(path), apply=apply)

        scanned = 0
        changed = 0
        changed_payload = 0
        changed_error = 0
        archive_rows = 0

        for row in _iter_rows(ro, "capture_outbox"):
            scanned += 1
            payload_before = str(row["payload"])
            error_before = str(row["last_error"])
            payload_after = _scrub_payload(payload_before)
            error_after = _scrub_string(error_before)
            if payload_after != payload_before or error_after != error_before:
                changed += 1
                if payload_after != payload_before:
                    changed_payload += 1
                if error_after != error_before:
                    changed_error += 1

        if "capture_outbox_archive" in tables:
            archive_rows = int(
                ro.execute("SELECT COUNT(*) FROM capture_outbox_archive").fetchone()[0]
            )
    finally:
        ro.close()

    if apply and changed:
        lock_path = path.with_suffix(path.suffix + ".secret-scrub.lock")
        with MaintenanceLock(lock_path):
            rw = _open_rw(path)
            try:
                def _write() -> None:
                    rw.execute("BEGIN IMMEDIATE")
                    runtime_tables = {
                        r[0] for r in rw.execute("SELECT name FROM sqlite_master WHERE type='table'")
                    }
                    for table in ("capture_outbox", "capture_outbox_archive"):
                        if table not in runtime_tables:
                            continue
                        for row in _iter_rows(rw, table):
                            payload_before = str(row["payload"])
                            error_before = str(row["last_error"])
                            payload_after = _scrub_payload(payload_before)
                            error_after = _scrub_string(error_before)
                            if payload_after == payload_before and error_after == error_before:
                                continue
                            rw.execute(
                                f"""
                                UPDATE {table}
                                SET payload = ?,
                                    last_error = CASE WHEN ? = '' THEN NULL ELSE ? END
                                WHERE id = ?
                                """,
                                (
                                    payload_after,
                                    error_after,
                                    error_after,
                                    int(row["id"]),
                                ),
                            )
                    rw.commit()

                with_sqlite_retry(_write, op_label="scrub_capture_outbox")
                rw.execute("VACUUM")
            except Exception:
                rw.rollback()
                raise
            finally:
                rw.close()

    return OutboxSecretScrubReport(
        outbox_db=str(path),
        apply=apply,
        scanned_rows=scanned,
        changed_rows=changed,
        changed_payload_rows=changed_payload,
        changed_error_rows=changed_error,
        archive_rows=archive_rows,
    )
