"""Ponte claude-mem → hive_mind (doc 08) — preserva project, idempotente, quarentena.

Testa contra SQLite REAL (R1/R5): fonte (claude-mem) e destino (hive_mind) em arquivos
temporários, com get_connection/open_claude_mem monkeypatchados p/ abrir conexões frescas
(fiel ao runtime, onde cada chamada abre/fecha sua conexão)."""
import sqlite3
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS.parent))

from scripts.services import claude_mem_bridge as br

_HM_DDL = """
CREATE TABLE observations (
    id TEXT PRIMARY KEY, session_id TEXT, project TEXT, type TEXT, title TEXT,
    content TEXT, created_at DATETIME, neuron_id TEXT, metadata JSON,
    archived INTEGER DEFAULT 0
);
CREATE TABLE neurons (id TEXT PRIMARY KEY, label TEXT, type TEXT);
"""
_CM_DDL = """
CREATE TABLE observations (
    id INTEGER PRIMARY KEY, project TEXT, text TEXT, narrative TEXT, title TEXT,
    type TEXT, created_at TEXT, created_at_epoch INTEGER, content_hash TEXT
);
"""


def _connect(path: Path) -> sqlite3.Connection:
    c = sqlite3.connect(str(path))
    c.row_factory = sqlite3.Row
    return c


@pytest.fixture()
def hm_path(tmp_path, monkeypatch):
    p = tmp_path / "hive_mind.db"
    c = _connect(p); c.executescript(_HM_DDL); c.commit(); c.close()
    monkeypatch.setattr(br, "get_connection", lambda: _connect(p))
    monkeypatch.setattr(br, "ensure_migrations", lambda c: None)
    return p


@pytest.fixture()
def cm_path(tmp_path, monkeypatch):
    p = tmp_path / "claude-mem.db"
    c = _connect(p); c.executescript(_CM_DDL)
    c.executemany(
        "INSERT INTO observations (id,project,text,narrative,title,type,created_at,created_at_epoch,content_hash)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        [(1, "ComfyUI", "node novo", None, "Node", "decision", "2026-06-10", 1000, "h-comfy"),
         (2, "Thoth", "rota auth", None, "Auth", "learning", "2026-06-11", 1001, "h-thoth"),
         (3, "Hive-Mind", "tweak dream", None, "Dream", "decision", "2026-06-12", 1002, "h-hive"),
         (4, None, "sem projeto", None, "Sem", "event", "2026-06-13", 1003, "h-null")])
    c.commit(); c.close()
    monkeypatch.setattr(br, "open_claude_mem", lambda db_path=None: _connect(p))
    return p


def _count(path, where="1=1"):
    c = _connect(path)
    try:
        return c.execute(f"SELECT COUNT(*) FROM observations WHERE {where}").fetchone()[0]
    finally:
        c.close()


def test_bridge_preserva_project(hm_path, cm_path):
    stats = br.bridge(cm_db=cm_path)
    assert stats["inserted"] == 4
    c = _connect(hm_path)
    projs = dict(c.execute("SELECT project, COUNT(*) FROM observations GROUP BY project").fetchall())
    c.close()
    assert projs.get("ComfyUI") == 1 and projs.get("Thoth") == 1
    assert _count(hm_path, "project IS NULL") == 0   # null vira default, não fica NULL


def test_default_claude_mem_db_aponta_para_global(monkeypatch):
    monkeypatch.delenv("CLAUDE_MEM_DB", raising=False)
    assert br.CLAUDE_MEM_DB == br.Path.home() / ".claude-mem" / "claude-mem.db"


def test_bridge_idempotente(hm_path, cm_path):
    br.bridge(cm_db=cm_path)
    stats2 = br.bridge(cm_db=cm_path)
    assert stats2["inserted"] == 0 and stats2["skipped"] == 4
    assert _count(hm_path) == 4   # não duplica


def test_bridge_id_deterministico(hm_path, cm_path):
    br.bridge(cm_db=cm_path)
    c = _connect(hm_path)
    ids = [r[0] for r in c.execute("SELECT id FROM observations")]
    c.close()
    assert all(i.startswith("cm-") for i in ids)
    assert "cm-h-comfy" in ids


def test_dry_run_nao_escreve(hm_path, cm_path):
    stats = br.bridge(cm_db=cm_path, dry_run=True)
    assert stats["inserted"] == 4
    assert _count(hm_path) == 0


def test_quarantine_legacy(hm_path, cm_path):
    c = _connect(hm_path)
    c.execute("INSERT INTO observations (id, project, archived) VALUES ('junk1', NULL, 0)")
    c.execute("INSERT INTO observations (id, project, archived) VALUES ('junk2', NULL, 0)")
    c.commit(); c.close()
    n = br.quarantine_legacy()
    assert n == 2
    assert _count(hm_path, "archived=2") == 2
    # bridged (cm-*) nunca é quarentenado
    br.bridge(cm_db=cm_path)
    assert _count(hm_path, "id LIKE 'cm-%' AND archived=2") == 0


def _identity_envelope(**overrides):
    envelope = {
        "project_id": "root/canonical-2fbe6cbe9d3a",
        "project_name": "Canonical Project",
        "workspace_root": r"D:\\Canonical",
        "repository_root": r"D:\\Canonical",
        "repository_remote": "github.com/example/canonical-project",
        "git_common_dir": r"D:\\Canonical\\.git",
        "worktree_name": "canonical-worktree",
        "branch": "feature/identity",
        "provider": "copilot",
        "surface": "ide-extension",
        "resolution_method": "git_remote",
        "resolution_confidence": 1.0,
        "referenced_projects": [],
        "schema_version": 1,
        "future_optional_field": "preserved",
    }
    envelope.update(overrides)
    return envelope


def test_bridge_uses_versioned_identity_envelope_for_project_and_workspace(hm_path, cm_path):
    import json

    hm = _connect(hm_path)
    hm.execute("ALTER TABLE observations ADD COLUMN workspace_id TEXT")
    hm.commit()
    hm.close()

    cm = _connect(cm_path)
    cm.execute("ALTER TABLE observations ADD COLUMN metadata TEXT")
    cm.execute("ALTER TABLE observations ADD COLUMN memory_session_id TEXT")
    cm.execute(
        "UPDATE observations SET project=?, memory_session_id=?, metadata=? WHERE id=1",
        (
            "provider-free-form-label",
            "source-session-1",
            json.dumps({"project_identity": _identity_envelope()}),
        ),
    )
    cm.commit()
    cm.close()

    stats = br.bridge(cm_db=cm_path, source_ids=["claude-mem:observations:1"])

    hm = _connect(hm_path)
    row = hm.execute(
        "SELECT project, workspace_id, metadata FROM observations WHERE id='cm-h-comfy'"
    ).fetchone()
    hm.close()
    metadata = json.loads(row["metadata"])
    assert row["workspace_id"] == "root/canonical-2fbe6cbe9d3a"
    assert row["project"] == "Canonical Project"
    assert metadata["project_id"] == "root/canonical-2fbe6cbe9d3a"
    assert metadata["project_name"] == "Canonical Project"
    assert metadata["provider"] == "copilot"
    assert metadata["surface"] == "ide-extension"
    assert metadata["branch"] == "feature/identity"
    assert metadata["worktree_name"] == "canonical-worktree"
    assert metadata["source_session"] == "source-session-1"
    assert metadata["identity_status"] == "canonical"
    assert metadata["project_identity"]["future_optional_field"] == "preserved"
    assert stats["by_identity"] == {"canonical": 1}


def test_bridge_marks_legacy_identity_unclassified_without_inference(hm_path, cm_path):
    import json

    hm = _connect(hm_path)
    hm.execute("ALTER TABLE observations ADD COLUMN workspace_id TEXT")
    hm.commit()
    hm.close()

    stats = br.bridge(cm_db=cm_path, source_ids=["claude-mem:observations:2"])

    hm = _connect(hm_path)
    row = hm.execute(
        "SELECT project, workspace_id, metadata FROM observations WHERE id='cm-h-thoth'"
    ).fetchone()
    hm.close()
    metadata = json.loads(row["metadata"])
    assert row["project"] == "Thoth"
    assert row["workspace_id"] == "unclassified/legacy"
    assert metadata["project_id"] == "unclassified/legacy"
    assert metadata["identity_status"] == "legacy"
    assert metadata["legacy_identity"] is True
    assert metadata["project_id"] not in {"thoth", "provider", "surface"}
    assert stats["by_identity"] == {"legacy": 1}


def test_bridge_heals_posted_registry_when_row_already_exists_in_umc(
    hm_path, cm_path, tmp_path
):
    from hive_mind.capture.identity_store import DeliveryState, IdentityStore

    content_session_id = "sid-bridge-heal"
    memory_session_id = "memory-bridge-heal"

    hm = _connect(hm_path)
    hm.execute("ALTER TABLE observations ADD COLUMN workspace_id TEXT")
    hm.execute(
        """
        INSERT INTO observations (
            id, session_id, project, type, title, content, created_at, metadata, archived, workspace_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "cm-h-comfy",
            None,
            "Canonical Project",
            "decision",
            "Node",
            "node novo",
            "2026-06-10",
            "{}",
            0,
            "root/canonical-2fbe6cbe9d3a",
        ),
    )
    hm.commit()
    hm.close()

    cm = _connect(cm_path)
    cm.execute("ALTER TABLE observations ADD COLUMN metadata TEXT")
    cm.execute("ALTER TABLE observations ADD COLUMN memory_session_id TEXT")
    cm.execute(
        """
        CREATE TABLE sdk_sessions (
            id INTEGER PRIMARY KEY,
            content_session_id TEXT UNIQUE NOT NULL,
            memory_session_id TEXT UNIQUE NOT NULL,
            project TEXT
        )
        """
    )
    cm.execute(
        "UPDATE observations SET memory_session_id=?, metadata=? WHERE id=1",
        (memory_session_id, "{}"),
    )
    cm.execute(
        """
        INSERT INTO sdk_sessions(content_session_id, memory_session_id, project)
        VALUES (?, ?, ?)
        """,
        (content_session_id, memory_session_id, "Canonical Project"),
    )
    cm.commit()
    cm.close()

    store = IdentityStore(path=tmp_path / "capture-identities.db")
    envelope = _identity_envelope(
        provider="codex",
        surface="cli",
        project_id="root/canonical-2fbe6cbe9d3a",
        project_name="Canonical Project",
    )
    store.record_pending(
        content_session_id=content_session_id,
        provider="codex",
        surface="cli",
        project_id="root/canonical-2fbe6cbe9d3a",
        project_name="Canonical Project",
        identity=envelope,
    )
    store.mark_posted(content_session_id)

    stats = br.bridge(
        cm_db=cm_path,
        identity_store=store,
        source_ids=["claude-mem:observations:1"],
    )

    assert stats["inserted"] == 0
    assert stats["skipped"] == 1
    healed = store.get(content_session_id)
    assert healed is not None
    assert healed.delivery_state is DeliveryState.BRIDGED
    assert healed.observed_at is not None
    assert healed.bridged_at is not None


def test_bridge_rejects_explicit_default_project_before_opening_databases(
    cm_path, monkeypatch
):
    def unexpected_call(*args, **kwargs):
        raise AssertionError("bridge opened a database before rejecting default_project")

    monkeypatch.setattr(br, "get_connection", unexpected_call)
    monkeypatch.setattr(br, "open_claude_mem", unexpected_call)

    with pytest.raises(ValueError, match="project_identity"):
        br.bridge(cm_db=cm_path, default_project="Customer-A")


def test_wrapper_serializes_hook_sync_call_and_restore(monkeypatch):
    import threading

    with br._HOOK_LOCK:
        assert br._call_with_synced_hooks(lambda: "reentrant") == "reentrant"

    original = (
        br._core_bridge.get_connection,
        br._core_bridge.ensure_migrations,
        br._core_bridge.open_claude_mem,
    )
    a_entered = threading.Event()
    release_a = threading.Event()
    b_called = threading.Event()
    errors = []
    results = {}

    def get_a():
        return "get-a"

    def migrate_a(conn):
        return "migrate-a"

    def open_a(path=None):
        return "open-a"

    def get_b():
        return "get-b"

    def migrate_b(conn):
        return "migrate-b"

    def open_b(path=None):
        return "open-b"

    hooks_a = (get_a, migrate_a, open_a)
    hooks_b = (get_b, migrate_b, open_b)

    def fake_bridge(*, label):
        expected = hooks_a if label == "A" else hooks_b
        actual = (
            br._core_bridge.get_connection,
            br._core_bridge.ensure_migrations,
            br._core_bridge.open_claude_mem,
        )
        if actual != expected:
            raise AssertionError(f"{label} observed crossed hooks")
        if label == "A":
            a_entered.set()
            if not release_a.wait(3):
                raise AssertionError("A was not released")
            actual_after_wait = (
                br._core_bridge.get_connection,
                br._core_bridge.ensure_migrations,
                br._core_bridge.open_claude_mem,
            )
            if actual_after_wait != hooks_a:
                raise AssertionError("A hooks changed while its call was active")
        else:
            b_called.set()
        return label

    monkeypatch.setattr(br._core_bridge, "bridge", fake_bridge)
    monkeypatch.setattr(br, "get_connection", get_a)
    monkeypatch.setattr(br, "ensure_migrations", migrate_a)
    monkeypatch.setattr(br, "open_claude_mem", open_a)

    def invoke(label):
        try:
            results[label] = br.bridge(label=label)
        except BaseException as error:  # retain worker failures for the main thread
            errors.append(error)

    thread_a = threading.Thread(target=invoke, args=("A",))
    thread_b = threading.Thread(target=invoke, args=("B",))
    thread_a.start()
    assert a_entered.wait(2)

    monkeypatch.setattr(br, "get_connection", get_b)
    monkeypatch.setattr(br, "ensure_migrations", migrate_b)
    monkeypatch.setattr(br, "open_claude_mem", open_b)
    thread_b.start()
    try:
        assert not b_called.wait(0.2)
        assert (
            br._core_bridge.get_connection,
            br._core_bridge.ensure_migrations,
            br._core_bridge.open_claude_mem,
        ) == hooks_a
    finally:
        release_a.set()
        thread_a.join(3)
        thread_b.join(3)

    assert not thread_a.is_alive()
    assert not thread_b.is_alive()
    assert errors == []
    assert results == {"A": "A", "B": "B"}
    assert (
        br._core_bridge.get_connection,
        br._core_bridge.ensure_migrations,
        br._core_bridge.open_claude_mem,
    ) == original
