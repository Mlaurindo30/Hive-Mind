import json
import sqlite3
from pathlib import Path

from hive_mind.maintenance.scrub_capture_outbox import scrub_capture_outbox
from scripts.utils.sanitizer import sanitize


def _init_outbox(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE capture_outbox (
            id INTEGER PRIMARY KEY,
            dedupe_key TEXT NOT NULL,
            provider TEXT NOT NULL,
            session_id TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            payload TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            next_retry_at REAL NOT NULL DEFAULT 0,
            last_error TEXT,
            created_at REAL NOT NULL,
            delivered_at REAL,
            dead_letter_at REAL,
            claim_owner TEXT,
            claim_until REAL
        )
        """
    )
    payload = {
        "content": (
            'Authorization: Bearer abc.def.ghi\n'
            'OPENAI_API_KEY=sk-proj-abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890\n'
            'ANTHROPIC_API_KEY=sk-ant-abcdefghijklmnopqrstuvwxyz1234567890\n'
            'google=AIzaSyABCDEFGHIJKLMNOPQRSTUVWXY123456789'
        )
    }
    conn.execute(
        """
        INSERT INTO capture_outbox (
            id, dedupe_key, provider, session_id, occurred_at, payload,
            attempts, next_retry_at, last_error, created_at,
            delivered_at, dead_letter_at, claim_owner, claim_until
        ) VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?, 0, NULL, NULL, NULL, NULL)
        """,
        (
            1,
            "a",
            "claude",
            "s1",
            "2026-07-20T00:00:00+00:00",
            json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
            "last error with sk-proj-abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890",
        ),
    )
    conn.commit()
    conn.close()


def test_sanitizer_uses_central_redactor_for_secret_shaped_strings():
    text = (
        'Authorization: Bearer abc.def.ghi '
        'OPENAI_API_KEY=sk-proj-abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890 '
        'ANTHROPIC_API_KEY=sk-ant-abcdefghijklmnopqrstuvwxyz1234567890'
    )
    out = sanitize(text)
    assert "Bearer abc.def.ghi" not in out
    assert "sk-proj-" not in out
    assert "sk-ant-" not in out


def test_scrub_capture_outbox_dry_run_detects_rows_that_would_change(tmp_path):
    db = tmp_path / "capture-outbox.db"
    _init_outbox(db)

    report = scrub_capture_outbox(outbox_db=db, apply=False)
    assert report.scanned_rows == 1
    assert report.changed_rows == 1
    assert report.changed_payload_rows == 1
    assert report.changed_error_rows == 1


def test_scrub_capture_outbox_apply_rewrites_secret_shaped_material(tmp_path):
    db = tmp_path / "capture-outbox.db"
    _init_outbox(db)

    report = scrub_capture_outbox(outbox_db=db, apply=True)
    assert report.changed_rows == 1

    conn = sqlite3.connect(db)
    payload, last_error = conn.execute(
        "SELECT payload, last_error FROM capture_outbox WHERE id = 1"
    ).fetchone()
    conn.close()

    assert "sk-proj-" not in payload
    assert "sk-ant-" not in payload
    assert "Bearer abc.def.ghi" not in payload
    assert "AIzaSy" not in payload
    assert "sk-proj-" not in (last_error or "")
