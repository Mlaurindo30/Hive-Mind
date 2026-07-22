"""M14 — one run, from a real session to a canonical workspace_id.

Not two proofs stitched together. A single execution: a session with a tool
call goes through the real ingest, is recorded, posted over real HTTP to a
disposable worker, summarised by a local model into a real observation, found
again through the declared foreign key, and bridged into a temporary UMC —
where the workspace id is the one the ingest decided, minutes earlier, before
the post went out.

Nothing here is stubbed. No `_post` monkeypatch, no manually inserted
observation, no metadata written straight into a database so a later assertion
can find it.
"""
from __future__ import annotations

import importlib
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import time
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LIVE_PORT = 37700
LIVE_STORE = Path.home() / ".claude-mem" / "claude-mem.db"
PLUGIN_CACHE = Path.home() / ".claude" / "plugins" / "cache" / "thedotmack" / "claude-mem"
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")


def _worker_script():
    if not PLUGIN_CACHE.is_dir():
        return None
    for version in sorted((p for p in PLUGIN_CACHE.iterdir() if p.is_dir()),
                          key=lambda p: p.name, reverse=True):
        candidate = version / "scripts" / "worker-service.cjs"
        if candidate.is_file():
            return candidate
    return None


def _bun():
    found = shutil.which("bun")
    if found:
        return found
    packages = Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages"
    for path in packages.glob("Oven-sh.Bun*/**/bun.exe") if packages.is_dir() else ():
        return str(path)
    return None


def _local_model():
    import urllib.request

    try:
        with urllib.request.urlopen(f"{OLLAMA_HOST}/api/tags", timeout=5) as reply:
            installed = {m["name"] for m in json.load(reply).get("models", [])}
    except Exception:
        return None
    for candidate in ("qwen2.5:3b", "gemma3:4b", "granite4.1:8b"):
        if candidate in installed:
            return candidate
    return None


WORKER, BUN, MODEL = _worker_script(), _bun(), _local_model()

pytestmark = pytest.mark.skipif(
    not (WORKER and BUN and MODEL),
    reason="needs the claude-mem worker, bun, and a local Ollama chat model",
)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _git(path: Path, *args):
    return subprocess.run(["git", "-C", str(path), *args], check=True,
                          capture_output=True, text=True)


def _repo(path: Path) -> Path:
    path.mkdir(parents=True)
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.email", "t@t")
    _git(path, "config", "user.name", "t")
    (path / "README.md").write_text(f"# {path.name}\n\nA temporary project.\n",
                                    encoding="utf-8")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "init")
    return path


@pytest.fixture(scope="module")
def chain(tmp_path_factory):
    """Everything temporary: worker, store, registry, UMC, and two projects."""
    from hive_mind.capture.worker_env import build_environment

    base = tmp_path_factory.mktemp("m14-e2e")
    data_dir = base / "claude-mem"
    data_dir.mkdir()
    port = _free_port()
    assert port != LIVE_PORT

    data_dir.joinpath("settings.json").write_text(json.dumps({
        "CLAUDE_MEM_RUNTIME": "worker",
        "CLAUDE_MEM_DATA_DIR": str(data_dir),
        "CLAUDE_MEM_WORKER_HOST": "127.0.0.1",
        "CLAUDE_MEM_WORKER_PORT": str(port),
        "CLAUDE_MEM_CHROMA_ENABLED": "false",
        "CLAUDE_MEM_PROVIDER": "openrouter",
        "CLAUDE_MEM_OPENROUTER_BASE_URL": f"{OLLAMA_HOST}/v1",
        "CLAUDE_MEM_OPENROUTER_API_KEY": "local",
        "CLAUDE_MEM_OPENROUTER_MODEL": MODEL,
    }), encoding="utf-8")

    env = build_environment(base=base / "iso", extra={
        "CLAUDE_MEM_DATA_DIR": str(data_dir),
        "CLAUDE_MEM_WORKER_HOST": "127.0.0.1",
        "CLAUDE_MEM_WORKER_PORT": str(port),
        "CLAUDE_MEM_CHROMA_ENABLED": "false",
    })
    log = (data_dir / "worker.log").open("w", encoding="utf-8")
    process = subprocess.Popen([BUN, str(WORKER)], env=env, stdout=log,
                               stderr=subprocess.STDOUT, cwd=str(ROOT))
    deadline = time.time() + 90
    while time.time() < deadline:
        with socket.socket() as probe:
            probe.settimeout(0.5)
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                break
        if process.poll() is not None:
            log.close()
            pytest.skip("worker exited: " + (data_dir / "worker.log").read_text(
                encoding="utf-8", errors="replace")[-600:])
        time.sleep(1)
    else:
        process.terminate()
        log.close()
        pytest.skip("worker never became ready")

    yield {
        "base": base, "data_dir": data_dir, "port": port,
        "cm_db": data_dir / "claude-mem.db",
        "registry_db": base / "identities.db",
        "umc_home": base / "umc",
        "project_a": _repo(base / "project-alpha"),
        "project_b": _repo(base / "project-beta"),
        "marker": f"HM-M14-{int(time.time())}-{uuid.uuid4().hex[:8]}",
    }

    process.terminate()
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        process.kill()
    log.close()


@pytest.fixture(scope="module")
def registry(chain):
    from hive_mind.capture.identity_store import IdentityStore

    with IdentityStore(chain["registry_db"]) as store:
        yield store


def _session(marker: str, cwd: Path, sid: str, raw_label: str):
    """A session with real activity, so the model has something to observe."""
    return {
        "sid": sid,
        "cwd": str(cwd),
        "surface": "cli",
        "project": raw_label,
        "prompt": f"Read README.md and report its heading. Marker {marker}.",
        "turns": [
            {"tool_name": "Read", "tool_input": {"file_path": "README.md"},
             "tool_response": (cwd / "README.md").read_text(encoding="utf-8")},
            {"tool_name": "Message", "tool_input": {},
             "tool_response": (f"The heading is '# {cwd.name}'. "
                               f"Marker {marker}.")},
        ],
        "last": f"The heading is '# {cwd.name}'. Marker {marker}.",
    }


def _ingest(chain, registry, sid, project, raw_label="rotulo-invalido"):
    os.environ["CLAUDE_MEM_WORKER_PORT"] = str(chain["port"])
    os.environ["CLAUDE_MEM_WORKER_HOST"] = "127.0.0.1"
    from hive_mind.capture import engine

    importlib.reload(engine)
    assert str(LIVE_PORT) not in engine.BASE
    from hive_mind.capture.ingest import ingest

    store = engine.SeenStore(chain["data_dir"] / f"seen-{sid}.db")
    try:
        return ingest("codex", _session(chain["marker"], project, sid, raw_label),
                      store, identity_store=registry)
    finally:
        store.close()


def _wait_for_observation(chain, timeout=240):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if chain["cm_db"].is_file():
            with sqlite3.connect(f"file:{chain['cm_db'].as_posix()}?mode=ro",
                                 uri=True) as connection:
                connection.row_factory = sqlite3.Row
                try:
                    rows = connection.execute(
                        "SELECT id, memory_session_id, project, metadata"
                        " FROM observations").fetchall()
                except sqlite3.OperationalError:
                    rows = []
            if rows:
                return rows
        time.sleep(3)
    return []


def _run_bridge(chain, registry, marker_only=True):
    """The production bridge, against temporary databases."""
    os.environ["SINAPSE_HOME"] = str(chain["umc_home"])
    os.environ["CLAUDE_MEM_DB"] = str(chain["cm_db"])
    chain["umc_home"].mkdir(exist_ok=True)
    (chain["umc_home"] / "core").mkdir(exist_ok=True)
    shutil.copy2(ROOT / "core" / "umc_schema.sql", chain["umc_home"] / "core")

    import core.database as database

    importlib.reload(database)
    database.init_db()
    from core.knowledge import claude_mem_bridge as bridge

    importlib.reload(bridge)
    return bridge.bridge(cm_db=chain["cm_db"], limit=100,
                         identity_store=registry), database


# ---------------------------------------------------------------------------
# The single run
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def executed(chain, registry):
    """Run the chain once; every assertion below reads its result."""
    sid = f"m14-{chain['marker']}"
    emitted = _ingest(chain, registry, sid, chain["project_a"])
    observations = _wait_for_observation(chain)
    stats, database = _run_bridge(chain, registry)
    return {"sid": sid, "emitted": emitted, "observations": observations,
            "stats": stats, "database": database}


class TestTheChainRanEndToEnd:
    def test_exactly_one_decision_exists_for_the_session(self, executed, registry):
        assert registry.get(executed["sid"]) is not None
        total = registry._connection.execute(
            "SELECT COUNT(*) FROM capture_identity_decisions"
            " WHERE content_session_id=?", (executed["sid"],)).fetchone()[0]
        assert total == 1

    def test_the_worker_produced_an_observation(self, executed):
        assert executed["observations"], "no observation was generated"

    def test_the_observation_reaches_our_session_by_foreign_key(self, chain,
                                                                executed):
        from hive_mind.capture.observation_identity import content_session_id_for

        with sqlite3.connect(f"file:{chain['cm_db'].as_posix()}?mode=ro",
                             uri=True) as connection:
            connection.row_factory = sqlite3.Row
            found = content_session_id_for(
                connection, executed["observations"][0]["memory_session_id"])
        assert found == executed["sid"]

    def test_the_decision_reached_bridged(self, executed, registry):
        from hive_mind.capture.identity_store import DeliveryState

        assert registry.get(executed["sid"]).delivery_state is DeliveryState.BRIDGED

    def test_every_state_was_stamped_in_order(self, executed, registry):
        decision = registry.get(executed["sid"])
        assert decision.posted_at and decision.observed_at and decision.bridged_at
        assert decision.posted_at <= decision.observed_at <= decision.bridged_at


class TestTheIdentityThatArrived:
    def test_the_umc_workspace_id_is_the_decided_project_id(self, executed,
                                                            registry):
        decision = registry.get(executed["sid"])
        with sqlite3.connect(executed["database"].DB_PATH) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT project, workspace_id, metadata FROM observations"
            ).fetchall()
        assert rows, "the bridge wrote nothing"
        assert {row["workspace_id"] for row in rows} == {decision.project_id}

    def test_the_project_name_is_canonical(self, executed, registry):
        assert registry.get(executed["sid"]).project_name == "project-alpha"

    def test_the_raw_label_was_never_authority(self, executed, registry):
        decision = registry.get(executed["sid"])
        assert decision.raw_project_label == "rotulo-invalido"
        assert decision.project_id != "rotulo-invalido"
        with sqlite3.connect(executed["database"].DB_PATH) as connection:
            values = {row[0] for row in connection.execute(
                "SELECT workspace_id FROM observations")}
        assert "rotulo-invalido" not in values

    def test_the_identity_came_from_the_registry(self, executed):
        with sqlite3.connect(executed["database"].DB_PATH) as connection:
            connection.row_factory = sqlite3.Row
            metadata = [json.loads(row["metadata"] or "{}") for row in
                        connection.execute("SELECT metadata FROM observations")]
        assert any(entry.get("identity_origin") == "registry" for entry in metadata)
        assert all(entry.get("identity_status") == "canonical" for entry in metadata)


class TestRepeatingItChangesNothing:
    def test_a_second_bridge_run_does_not_duplicate(self, chain, registry,
                                                    executed):
        before = executed["database"].DB_PATH
        with sqlite3.connect(before) as connection:
            first = connection.execute(
                "SELECT COUNT(*) FROM observations").fetchone()[0]
        _run_bridge(chain, registry)
        with sqlite3.connect(before) as connection:
            second = connection.execute(
                "SELECT COUNT(*) FROM observations").fetchone()[0]
        assert second == first

    def test_a_reopened_registry_still_answers(self, chain, executed):
        """The restart between post and bridge that a real run would have."""
        from hive_mind.capture.identity_store import IdentityStore

        with IdentityStore(chain["registry_db"]) as reopened:
            decision = reopened.get(executed["sid"])
        assert decision is not None and decision.project_name == "project-alpha"


class TestIsolation:
    def test_project_b_is_a_different_identity(self, chain, registry, executed):
        sid_b = f"m14b-{chain['marker']}"
        _ingest(chain, registry, sid_b, chain["project_b"])
        a = registry.get(executed["sid"])
        b = registry.get(sid_b)
        assert b is not None
        assert a.project_id != b.project_id
        assert b.project_name == "project-beta"

    def test_neither_outbox_saw_the_marker(self, chain):
        outboxes = (
            Path(r"D:\Hive-Mind") / "logs" / "capture-outbox.db",
            Path.home() / ".claude-mem" / "capture.db",
        )
        for path in outboxes:
            if not path.is_file():
                continue
            with sqlite3.connect(f"file:{path.as_posix()}?mode=ro",
                                 uri=True) as connection:
                found = connection.execute(
                    "SELECT COUNT(*) FROM capture_outbox WHERE dedupe_key LIKE ?",
                    (f"%{chain['marker']}%",)).fetchone()[0]
            assert found == 0

    def test_the_live_store_never_saw_the_marker(self, chain):
        if not LIVE_STORE.is_file():
            pytest.skip("no live store")
        with sqlite3.connect(f"file:{LIVE_STORE.as_posix()}?mode=ro",
                             uri=True) as connection:
            found = connection.execute(
                "SELECT COUNT(*) FROM user_prompts WHERE prompt_text LIKE ?",
                (f"%{chain['marker']}%",)).fetchone()[0]
        assert found == 0


class TestTheDatabasesAreSound:
    def test_the_registry_verifies(self, registry):
        assert registry.verify() == []

    def test_the_umc_passes_integrity_and_foreign_keys(self, executed):
        with sqlite3.connect(executed["database"].DB_PATH) as connection:
            assert connection.execute(
                "PRAGMA integrity_check").fetchone()[0] == "ok"
            assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
