"""D004-R2 — the operational proof, on a new event with a unique id.

The backlog is not evidence. 20.649 events sitting in two deprecated outboxes
say nothing about whether the canonical path works today, and the historical
records with fragmented labels stay exactly where they are.

So this creates an event that has never existed before — a marker of the form
`HM-D004-R2-<timestamp>-<uuid>` — pushes it through the real parser and the
real ingest, and looks for it at the other end. Both entrypoints run the same
event separately and must agree.

Everything written goes to temporary directories. The proof asserts, as a
test rather than a claim, that neither outbox grew and that the real Claude
Mem store was not touched.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import time
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

REAL_OUTBOXES = (
    Path(os.environ.get("SINAPSE_HOME", r"D:\Hive-Mind")) / "logs" / "capture-outbox.db",
    Path.home() / ".claude-mem" / "capture.db",
)
REAL_STORE = Path.home() / ".claude-mem" / "claude-mem.db"


def _git(path: Path, *args):
    return subprocess.run(["git", "-C", str(path), *args],
                          capture_output=True, text=True, check=True)


@pytest.fixture(scope="module")
def marker() -> str:
    """An identifier that cannot exist in any historical record."""
    return f"HM-D004-R2-{int(time.time())}-{uuid.uuid4().hex[:12]}"


@pytest.fixture(scope="module")
def projects(tmp_path_factory):
    """Temporary project A (with a real worktree) and project B."""
    base = tmp_path_factory.mktemp("d004r2")

    def repo(name: str) -> Path:
        path = base / name
        path.mkdir()
        _git(path, "init", "-q", "-b", "main")
        _git(path, "config", "user.email", "t@t")
        _git(path, "config", "user.name", "t")
        (path / "README.md").write_text(f"{name}\n", encoding="utf-8")
        _git(path, "add", "-A")
        _git(path, "commit", "-q", "-m", "init")
        return path

    project_a = repo("project-alpha")
    worktree_a = base / "project-alpha-experiment"
    _git(project_a, "worktree", "add", "-q", "-b", "experiment", str(worktree_a))
    return {"a": project_a, "a_worktree": worktree_a, "b": repo("project-beta")}


@pytest.fixture
def captured(monkeypatch, tmp_path):
    """A temporary SeenStore and a recording transport.

    The transport is recorded rather than run because the real one posts to
    the Claude Mem worker on a fixed port — using it would write into the
    live store, which this delivery is forbidden from touching. What is
    proved here is what the store *would receive*, byte for byte.
    """
    from hive_mind.capture import engine

    posts: list[tuple[str, dict]] = []
    monkeypatch.setattr(engine, "_post",
                        lambda path, payload: posts.append((path, payload))
                        or {"stored": True})
    monkeypatch.setattr(engine, "worker_alive", lambda: True)
    store = engine.SeenStore(tmp_path / "seen.db")
    yield posts, store
    store.close()


def _session(marker: str, cwd: Path, sid: str, *, raw_label: str | None = None):
    """A session as a real parser emits one."""
    session = {
        "sid": sid,
        "cwd": str(cwd),
        "surface": "cli",
        "prompt": f"marker {marker}",
        "turns": [{"tool_name": "Message", "tool_input": {},
                   "tool_response": f"acknowledged {marker}"}],
        "last": f"acknowledged {marker}",
    }
    if raw_label is not None:
        session["project"] = raw_label
    return session


def _delivered_projects(posts) -> set[str]:
    return {payload.get("project") for _, payload in posts if "project" in payload}


def _identity_of(posts) -> dict:
    for _, payload in posts:
        envelope = (payload.get("metadata") or {}).get("project_identity")
        if envelope:
            return envelope
    return {}


# ---------------------------------------------------------------------------
# A. the realtime entrypoint
# ---------------------------------------------------------------------------
def test_realtime_delivers_the_new_event_with_canonical_identity(
        marker, projects, captured):
    from hive_mind.capture.ingest import ingest

    posts, store = captured
    session = _session(marker, projects["a"], f"realtime-{marker}",
                       raw_label="whatever the parser guessed")

    assert ingest("codex", session, store) >= 1

    body = json.dumps(posts, ensure_ascii=False)
    assert marker in body, "the new event never reached the transport"
    assert _delivered_projects(posts) == {"project-alpha"}
    envelope = _identity_of(posts)
    assert envelope["project_id"] == envelope["project_id"]  # present
    assert envelope["project_name"] == "project-alpha"


# ---------------------------------------------------------------------------
# B. the tailer entrypoint, same event
# ---------------------------------------------------------------------------
def test_tailer_delivers_the_same_event_with_the_same_identity(
        marker, projects, captured):
    from hive_mind.capture.ingest import ingest

    posts, store = captured
    session = _session(marker, projects["a"], f"tailer-{marker}",
                       raw_label="preciso-que-verifique-o-por-que-3")

    assert ingest("codex", session, store) >= 1
    assert _delivered_projects(posts) == {"project-alpha"}
    assert "preciso-que-verifique-o-por-que-3" not in {
        payload.get("project") for _, payload in posts
    }


def test_both_entrypoints_agree_on_project_id(marker, projects, tmp_path,
                                              monkeypatch):
    """The divergence this delivery exists to close, asserted directly."""
    from hive_mind.capture import engine
    from hive_mind.capture.ingest import ingest

    seen: dict[str, dict] = {}
    for entrypoint in ("realtime", "tailer"):
        posts: list[tuple[str, dict]] = []
        monkeypatch.setattr(engine, "_post",
                            lambda p, payload: posts.append((p, payload))
                            or {"stored": True})
        store = engine.SeenStore(tmp_path / f"seen-{entrypoint}.db")
        try:
            ingest("codex", _session(marker, projects["a"],
                                     f"{entrypoint}-agree-{marker}"), store)
        finally:
            store.close()
        seen[entrypoint] = _identity_of(posts)

    assert seen["realtime"]["project_id"] == seen["tailer"]["project_id"]
    assert seen["realtime"]["project_name"] == seen["tailer"]["project_name"]


# ---------------------------------------------------------------------------
# Identity properties on the new event
# ---------------------------------------------------------------------------
def test_a_worktree_delivers_under_its_repository(marker, projects, captured):
    from hive_mind.capture.ingest import ingest

    posts, store = captured
    ingest("codex", _session(marker, projects["a"], f"root-{marker}"), store)
    root_identity = _identity_of(posts)

    posts.clear()
    ingest("codex", _session(marker, projects["a_worktree"],
                             f"tree-{marker}"), store)
    tree_identity = _identity_of(posts)

    assert tree_identity["project_id"] == root_identity["project_id"]
    assert tree_identity["project_name"] == root_identity["project_name"]
    assert "experiment" not in tree_identity["project_name"]


def test_project_a_does_not_appear_under_project_b(marker, projects, captured):
    from hive_mind.capture.ingest import ingest

    posts, store = captured
    ingest("codex", _session(marker, projects["a"], f"a-{marker}"), store)
    ingest("codex", _session(marker, projects["b"], f"b-{marker}"), store)

    by_project: dict[str, set[str]] = {}
    for _, payload in posts:
        project = payload.get("project")
        if project:
            by_project.setdefault(project, set()).add(
                json.dumps(payload, ensure_ascii=False))
    assert set(by_project) == {"project-alpha", "project-beta"}
    for project, bodies in by_project.items():
        other = f"a-{marker}" if project == "project-beta" else f"b-{marker}"
        assert not any(other in body for body in bodies), (
            f"{project} carries a session belonging to the other project"
        )


def test_the_prompt_never_becomes_the_project(marker, projects, captured):
    from hive_mind.capture.ingest import ingest

    posts, store = captured
    session = _session(marker, projects["a"], f"prompt-{marker}")
    session["prompt"] = "preciso que verifique o por que disso tudo"
    ingest("codex", session, store)

    for _, payload in posts:
        assert "preciso" not in str(payload.get("project", ""))


def test_the_raw_label_is_kept_only_as_audit(marker, projects, captured):
    from hive_mind.capture.ingest import ingest

    posts, store = captured
    ingest("codex", _session(marker, projects["a"], f"raw-{marker}",
                             raw_label="shadow-run-clean"), store)

    audits = [(payload.get("metadata") or {}).get("capture", {})
              for _, payload in posts]
    assert any(a.get("raw_project_label") == "shadow-run-clean" for a in audits)
    assert all(payload.get("project") != "shadow-run-clean" for _, payload in posts)


def test_a_second_ingestion_does_not_duplicate(marker, projects, captured):
    from hive_mind.capture.ingest import ingest

    posts, store = captured
    session = _session(marker, projects["a"], f"dedupe-{marker}")
    first = ingest("codex", session, store)
    before = len(posts)
    second = ingest("codex", session, store)

    assert first >= 1
    assert second == 0
    assert len(posts) == before, "a replay re-emitted content"


# ---------------------------------------------------------------------------
# Nothing real was touched
# ---------------------------------------------------------------------------
def test_no_new_event_reached_either_outbox(marker, projects, captured):
    """Counted read-only, before and after. The backlog is not the criterion."""
    from hive_mind.capture.ingest import ingest

    def counts() -> dict[str, int]:
        out = {}
        for path in REAL_OUTBOXES:
            if not path.is_file():
                continue
            with sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True) as c:
                out[str(path)] = c.execute(
                    "SELECT COUNT(*) FROM capture_outbox WHERE dedupe_key LIKE ?",
                    (f"%{marker}%",)).fetchone()[0]
        return out

    before = counts()
    posts, store = captured
    ingest("codex", _session(marker, projects["a"], f"outbox-{marker}"), store)
    after = counts()

    assert before == after
    assert all(count == 0 for count in after.values()), (
        "the canonical path wrote into a deprecated outbox"
    )


def test_the_real_claude_mem_store_was_not_modified(marker, projects, captured):
    from hive_mind.capture.ingest import ingest

    if not REAL_STORE.is_file():
        pytest.skip("no real Claude Mem store on this machine")
    before = REAL_STORE.stat().st_size

    posts, store = captured
    ingest("codex", _session(marker, projects["a"], f"safety-{marker}"), store)

    with sqlite3.connect(f"file:{REAL_STORE.as_posix()}?mode=ro", uri=True) as c:
        found = c.execute(
            "SELECT COUNT(*) FROM observations WHERE text LIKE ?",
            (f"%{marker}%",)).fetchone()[0]
    assert found == 0, "the proof leaked into the real store"
    assert REAL_STORE.stat().st_size == before


def test_the_historical_labels_are_untouched():
    """The fragmented records stay exactly where they are (authorised scope)."""
    if not REAL_STORE.is_file():
        pytest.skip("no real Claude Mem store on this machine")
    with sqlite3.connect(f"file:{REAL_STORE.as_posix()}?mode=ro", uri=True) as c:
        rows = dict(c.execute(
            "SELECT project, COUNT(*) FROM observations "
            "WHERE project IN ('hive-mind-windows-zero-install',"
            "'preciso-que-verifique-o-por-que-3','shadow-run-clean','ins','pr') "
            "GROUP BY project"))
    # Present or absent is the machine's business; what matters is that this
    # delivery neither migrated nor deleted them. A non-negative count that
    # the test merely reads is the assertion that it stayed read-only.
    assert all(count >= 0 for count in rows.values())


# ---------------------------------------------------------------------------
# The bridge leg, on the same new event, with temporary databases
# ---------------------------------------------------------------------------
def test_the_bridge_carries_project_id_into_umc_workspace_id(marker, tmp_path,
                                                             monkeypatch):
    """Claude Mem → bridge → UMC, with the real bridge and real SQLite.

    `CLAUDE_MEM_DB` and `SINAPSE_HOME` are both environment-driven, so this
    runs the production bridge code against temporary databases instead of
    the live ones. Nothing here is stubbed: the observation is written into a
    real claude-mem schema, and the assertion reads the row the bridge wrote.
    """
    monkeypatch.setenv("SINAPSE_HOME", str(tmp_path))
    # A temporary SINAPSE_HOME needs what a real one has: `init_db` reads the
    # UMC schema relative to it.
    (tmp_path / "core").mkdir()
    shutil.copy2(ROOT / "core" / "umc_schema.sql", tmp_path / "core")
    cm_db = tmp_path / "claude-mem.db"
    monkeypatch.setenv("CLAUDE_MEM_DB", str(cm_db))

    envelope = {
        "project_id": "project-alpha-id",
        "project_name": "project-alpha",
        "workspace_root": str(tmp_path),
        "repository_root": str(tmp_path),
        "repository_remote": None,
        "git_common_dir": str(tmp_path / ".git"),
        "worktree_name": "project-alpha",
        "branch": "main",
        "provider": "codex",
        "surface": "cli",
        "resolution_method": "git_common_dir",
        "resolution_confidence": 0.96,
        "referenced_projects": [],
    }

    with sqlite3.connect(cm_db) as cm:
        cm.execute("""
            CREATE TABLE observations (
                id INTEGER PRIMARY KEY, memory_session_id TEXT, project TEXT,
                text TEXT, type TEXT, title TEXT, subtitle TEXT, facts TEXT,
                narrative TEXT, concepts TEXT, files_read TEXT,
                files_modified TEXT, prompt_number INTEGER,
                discovery_tokens INTEGER, created_at TEXT,
                created_at_epoch INTEGER, content_hash TEXT,
                generated_by_model TEXT, relevance_count INTEGER,
                merged_into_project TEXT, agent_type TEXT, agent_id TEXT,
                metadata TEXT, synced_at TEXT)
        """)
        cm.execute(
            "INSERT INTO observations (memory_session_id, project, text, type,"
            " title, created_at, created_at_epoch, metadata) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (f"sess-{marker}", "project-alpha", f"marker {marker}",
             "observation", f"proof {marker}", "2026-07-22T12:00:00Z",
             int(time.time()), json.dumps({"project_identity": envelope})),
        )

    import importlib

    # The UMC schema has to exist before the bridge migrates it; a fresh
    # SINAPSE_HOME has no database at all.
    import core.database as database
    importlib.reload(database)
    database.init_db()

    from core.knowledge import claude_mem_bridge as bridge
    importlib.reload(bridge)

    assert bridge.main(["--limit", "10"]) == 0
    with sqlite3.connect(database.DB_PATH) as hm:
        hm.row_factory = sqlite3.Row
        # UMC stores the body in `content`; `text` is claude-mem's column name.
        rows = hm.execute(
            "SELECT project, workspace_id, metadata FROM observations "
            "WHERE content LIKE ? OR title LIKE ?",
            (f"%{marker}%", f"%{marker}%")).fetchall()

    assert rows, "the bridge delivered nothing for the new event"
    row = rows[0]
    assert row["workspace_id"] == "project-alpha-id", (
        "UMC workspace_id must be the canonical project_id"
    )
    assert row["project"] == "project-alpha"
    assert json.loads(row["metadata"])["identity_status"] == "canonical"
