"""D004-R2W — the chain with the real worker, nothing stubbed.

The earlier proof recorded the HTTP POST instead of making it, so it showed
what the store *would* receive rather than a row existing. This closes that
gap: it starts a disposable Claude Mem worker of its own and runs the real
transport against it.

    provider session → parser → hive_mind.capture.ingest
                     → real HTTP → real worker → temporary claude-mem.db
                     → real bridge → temporary UMC

No `_post` monkeypatch, no manual INSERT of the row the test then looks for.
Isolation comes from configuration the worker already supports:
`resolveDataDir()` returns `CLAUDE_MEM_DATA_DIR` ahead of everything else,
and the pid file, settings and database all hang off that directory — so a
second worker on a free port cannot collide with the live one.
"""
from __future__ import annotations

import json
import os
import socket
import sqlite3
import subprocess
import time
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LIVE_STORE = Path.home() / ".claude-mem" / "claude-mem.db"
LIVE_PORT = 37700

PLUGIN_CACHE = Path.home() / ".claude" / "plugins" / "cache" / "thedotmack" / "claude-mem"


def _worker_script() -> Path | None:
    """The worker the runtime actually runs.

    `config/runtime.yaml` declares `python -m claude_mem.worker`, which does
    not exist — the live process is bun running `worker-service.cjs` from the
    plugin cache. Recorded here because the manifest and reality disagree.
    """
    if not PLUGIN_CACHE.is_dir():
        return None
    versions = sorted((p for p in PLUGIN_CACHE.iterdir() if p.is_dir()),
                      key=lambda p: p.name)
    for version in reversed(versions):
        candidate = version / "scripts" / "worker-service.cjs"
        if candidate.is_file():
            return candidate
    return None


def _bun() -> str | None:
    import shutil

    found = shutil.which("bun")
    if found:
        return found
    packages = (Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet"
                / "Packages")
    if packages.is_dir():
        for path in packages.glob("Oven-sh.Bun*/**/bun.exe"):
            return str(path)
    return None


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


WORKER = _worker_script()
BUN = _bun()

pytestmark = pytest.mark.skipif(
    WORKER is None or BUN is None,
    reason="claude-mem worker or bun runtime not installed on this machine",
)


@pytest.fixture(scope="module")
def isolated_worker(tmp_path_factory):
    """A disposable worker with its own data directory, port and database."""
    data_dir = tmp_path_factory.mktemp("claude-mem-isolated")
    port = _free_port()
    assert port != LIVE_PORT, "must never bind the runtime's port"

    (data_dir / "settings.json").write_text(json.dumps({
        "CLAUDE_MEM_RUNTIME": "worker",
        "CLAUDE_MEM_DATA_DIR": str(data_dir),
        "CLAUDE_MEM_WORKER_HOST": "127.0.0.1",
        "CLAUDE_MEM_WORKER_PORT": str(port),
        "CLAUDE_MEM_CHROMA_ENABLED": "false",
    }), encoding="utf-8")

    env = dict(os.environ)
    env.update({
        "CLAUDE_MEM_DATA_DIR": str(data_dir),
        "CLAUDE_MEM_WORKER_HOST": "127.0.0.1",
        "CLAUDE_MEM_WORKER_PORT": str(port),
        "CLAUDE_MEM_CHROMA_ENABLED": "false",
    })
    log = (data_dir / "worker.log").open("w", encoding="utf-8")
    process = subprocess.Popen([BUN, str(WORKER)], env=env, stdout=log,
                               stderr=subprocess.STDOUT, cwd=str(ROOT))

    deadline = time.time() + 60
    while time.time() < deadline:
        with socket.socket() as probe:
            probe.settimeout(0.5)
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                break
        if process.poll() is not None:
            log.close()
            pytest.skip("isolated worker exited: "
                        + (data_dir / "worker.log").read_text(
                            encoding="utf-8", errors="replace")[-800:])
        time.sleep(1)
    else:
        process.terminate()
        log.close()
        pytest.skip("isolated worker did not become ready in 60s")

    yield {"data_dir": data_dir, "port": port,
           "db": data_dir / "claude-mem.db"}

    process.terminate()
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        process.kill()
    log.close()


@pytest.fixture
def transport(isolated_worker, monkeypatch):
    """The real transport, pointed at the disposable worker.

    `BASE` is computed from the environment at import time, so this reloads
    the module rather than replacing `_post`. Retargeting is configuration;
    stubbing would defeat the point of this test.
    """
    import importlib

    monkeypatch.setenv("CLAUDE_MEM_WORKER_PORT", str(isolated_worker["port"]))
    monkeypatch.setenv("CLAUDE_MEM_WORKER_HOST", "127.0.0.1")
    from hive_mind.capture import engine

    importlib.reload(engine)
    assert engine.BASE.endswith(str(isolated_worker["port"]))
    assert str(LIVE_PORT) not in engine.BASE
    assert engine.worker_alive(), "the disposable worker is not answering"
    yield engine
    importlib.reload(engine)


def _wait_for(db: Path, sql: str, params: tuple, timeout: float = 120.0):
    """The worker processes asynchronously; poll its database read-only."""
    deadline = time.time() + timeout
    last: list = []
    while time.time() < deadline:
        if db.is_file():
            with sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True) as c:
                c.row_factory = sqlite3.Row
                try:
                    last = c.execute(sql, params).fetchall()
                except sqlite3.OperationalError:
                    last = []
            if last:
                return last
        time.sleep(2)
    return last


def _session(marker: str, cwd: Path, sid: str, raw_label: str):
    return {
        "sid": sid,
        "cwd": str(cwd),
        "surface": "cli",
        "prompt": f"marker {marker}",
        "project": raw_label,
        "turns": [{"tool_name": "Message", "tool_input": {},
                   "tool_response": f"acknowledged {marker}"}],
        "last": f"acknowledged {marker}",
    }


@pytest.fixture(scope="module")
def marker() -> str:
    return f"HM-D004-R2W-{int(time.time())}-{uuid.uuid4().hex[:8]}"


class TestTheRealWorkerStoresCanonicalIdentity:
    def test_the_worker_is_isolated_from_the_live_one(self, isolated_worker):
        assert isolated_worker["port"] != LIVE_PORT
        assert isolated_worker["db"] != LIVE_STORE
        # Its pid file lives in its own data dir, so no lock is shared.
        assert (isolated_worker["data_dir"] / "worker.pid").is_file()

    def test_a_new_event_is_stored_with_the_canonical_project(
            self, isolated_worker, transport, marker):
        """The row the earlier proof could only describe."""
        from hive_mind.capture.ingest import ingest

        store = transport.SeenStore(isolated_worker["data_dir"] / "seen.db")
        try:
            emitted = ingest("codex",
                             _session(marker, ROOT, f"iso-{marker}",
                                      raw_label="rotulo-livre-que-nao-vale"),
                             store)
        finally:
            store.close()
        assert emitted >= 1

        rows = _wait_for(
            isolated_worker["db"],
            "SELECT project FROM session_summaries WHERE project IS NOT NULL",
            (),
        )
        assert rows, "the worker stored nothing for the new event"
        projects = {row["project"] for row in rows}
        assert projects == {"Hive-Mind"}, (
            f"the stored project is not canonical: {projects}"
        )
        assert "rotulo-livre-que-nao-vale" not in projects

    def test_the_prompt_reached_the_store_verbatim(self, isolated_worker,
                                                   transport, marker):
        rows = _wait_for(
            isolated_worker["db"],
            "SELECT prompt_text FROM user_prompts WHERE prompt_text LIKE ?",
            (f"%{marker}%",),
        )
        assert rows, "the new event never reached the store"

    def test_a_replay_does_not_duplicate(self, isolated_worker, transport,
                                         marker):
        from hive_mind.capture.ingest import ingest

        store = transport.SeenStore(isolated_worker["data_dir"] / "seen.db")
        try:
            again = ingest("codex",
                           _session(marker, ROOT, f"iso-{marker}",
                                    raw_label="rotulo-livre-que-nao-vale"),
                           store)
        finally:
            store.close()
        assert again == 0, "re-ingesting the same session emitted again"


class TestNothingRealWasTouched:
    def test_the_live_store_never_saw_the_marker(self, isolated_worker,
                                                 transport, marker):
        if not LIVE_STORE.is_file():
            pytest.skip("no live store on this machine")
        with sqlite3.connect(f"file:{LIVE_STORE.as_posix()}?mode=ro",
                             uri=True) as c:
            found = c.execute(
                "SELECT COUNT(*) FROM user_prompts WHERE prompt_text LIKE ?",
                (f"%{marker}%",)).fetchone()[0]
        assert found == 0, "the isolated proof leaked into the live store"

    def test_neither_outbox_received_the_event(self, marker):
        outboxes = (
            Path(os.environ.get("SINAPSE_HOME", r"D:\Hive-Mind")) / "logs"
            / "capture-outbox.db",
            Path.home() / ".claude-mem" / "capture.db",
        )
        for path in outboxes:
            if not path.is_file():
                continue
            with sqlite3.connect(f"file:{path.as_posix()}?mode=ro",
                                 uri=True) as c:
                found = c.execute(
                    "SELECT COUNT(*) FROM capture_outbox WHERE dedupe_key LIKE ?",
                    (f"%{marker}%",)).fetchone()[0]
            assert found == 0, f"the canonical path wrote into {path.name}"


class TestTheManifestDisagreesWithReality:
    """Recorded as a finding, not fixed here — it belongs to D006-R2.

    `runtime.yaml` says the worker is `python -m claude_mem.worker`. That
    module is not importable, and the live process is bun running
    `worker-service.cjs`. A manifest that names a command nobody runs cannot
    be the single catalogue D006 wants it to be.
    """

    def test_the_declared_command_does_not_exist(self):
        import importlib.util

        assert importlib.util.find_spec("claude_mem") is None

    def test_the_real_worker_is_the_plugin_script(self):
        assert WORKER is not None and WORKER.name == "worker-service.cjs"
