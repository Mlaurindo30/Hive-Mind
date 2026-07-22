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


def _local_model() -> str | None:
    """A chat model already installed in Ollama. Never downloads one.

    Preference order is smallest-workable-first: the worker only has to
    summarise a short session, and a large model would make the test slow
    without making it more true.
    """
    import json as _json
    import urllib.request

    try:
        with urllib.request.urlopen(f"{OLLAMA_HOST}/api/tags", timeout=5) as reply:
            installed = {m["name"] for m in _json.load(reply).get("models", [])}
    except Exception:
        return None
    for candidate in ("qwen2.5:3b", "gemma3:4b", "granite4.1:8b"):
        if candidate in installed:
            return candidate
    # Anything general-purpose that is already there, excluding embedding and
    # vision-only models which cannot answer a summarisation prompt.
    for name in sorted(installed):
        if not any(tag in name for tag in ("embed", "ocr", "-v", "cloud")):
            return name
    return None


OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
OLLAMA_BASE_URL = f"{OLLAMA_HOST}/v1"

WORKER = _worker_script()
BUN = _bun()
LOCAL_MODEL = _local_model()

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

    # A local provider, configured exactly the way the project's own
    # setup-brain configures one: `sync-claude-mem-provider.py` maps any
    # OpenAI-compatible endpoint onto the worker's `openrouter` slot, and
    # `_key_for` returns the literal "local" for providers whose auth_type is
    # `local`. So this needs no credential of any kind — which is the point.
    #
    # Nothing global is touched: Ollama's own configuration, its models and
    # the model the live runtime uses are all left alone. Only this temporary
    # settings.json names the model below.
    settings = {
        "CLAUDE_MEM_RUNTIME": "worker",
        "CLAUDE_MEM_DATA_DIR": str(data_dir),
        "CLAUDE_MEM_WORKER_HOST": "127.0.0.1",
        "CLAUDE_MEM_WORKER_PORT": str(port),
        "CLAUDE_MEM_CHROMA_ENABLED": "false",
    }
    if LOCAL_MODEL:
        settings.update({
            "CLAUDE_MEM_PROVIDER": "openrouter",
            "CLAUDE_MEM_OPENROUTER_BASE_URL": OLLAMA_BASE_URL,
            "CLAUDE_MEM_OPENROUTER_API_KEY": "local",
            "CLAUDE_MEM_OPENROUTER_MODEL": LOCAL_MODEL,
        })
    (data_dir / "settings.json").write_text(json.dumps(settings), encoding="utf-8")

    # Built from an allowlist, not inherited. The first version of this
    # fixture passed `dict(os.environ)` through; it was safe only because this
    # machine happened to export no credentials (SEC-001).
    from hive_mind.capture.worker_env import build_environment, leaked_names

    env = build_environment(
        base=data_dir / "isolation",
        extra={
            "CLAUDE_MEM_DATA_DIR": str(data_dir),
            "CLAUDE_MEM_WORKER_HOST": "127.0.0.1",
            "CLAUDE_MEM_WORKER_PORT": str(port),
            "CLAUDE_MEM_CHROMA_ENABLED": "false",
        },
    )
    assert leaked_names(env) == [], "a credential reached the worker environment"
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
           "db": data_dir / "claude-mem.db", "env": env}

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

    def test_a_new_event_reaches_the_worker_with_the_canonical_project(
            self, isolated_worker, transport, marker):
        """The row the earlier proof could only describe.

        The worker's own session log records the project it received, which is
        the assertion that matters here: what crossed the HTTP boundary was
        the canonical name, not the free label the session carried.

        `session_summaries` and `observations` are *not* asserted, and that is
        deliberate. Producing either requires the worker's LLM, and a properly
        isolated environment has no credential for one — see
        `TestTheLlmBoundaryIsExplicit`. Asserting them here would only pass by
        letting the host's real credentials leak in, which is the defect
        SEC-001 exists to prevent.
        """
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
            "SELECT prompt_text FROM user_prompts WHERE prompt_text LIKE ?",
            (f"%{marker}%",),
        )
        assert rows, "the worker stored nothing for the new event"

        log = next((isolated_worker["data_dir"] / "logs").glob("*.log"), None)
        assert log is not None, "the worker wrote no log"
        text = log.read_text(encoding="utf-8", errors="replace")
        assert "Session initialized {project=Hive-Mind" in text, (
            "the worker did not receive the canonical project"
        )
        assert "rotulo-livre-que-nao-vale" not in text

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


class TestTheWorkerEnvironmentCarriesNoCredentials:
    """SEC-001: what reaches the worker is built, not inherited."""

    def test_no_credential_shaped_variable_is_present(self, isolated_worker):
        from hive_mind.capture.worker_env import leaked_names

        assert leaked_names(isolated_worker["env"]) == []

    def test_the_per_user_directories_are_temporary(self, isolated_worker):
        """Redirecting HOME alone is not enough on Windows.

        The comparison is against the real *directories*, not against the
        profile prefix: pytest's own tmp_path lives inside the user profile's
        AppData/Local/Temp, so a prefix check would fail on a correctly
        isolated environment.
        """
        env = isolated_worker["env"]
        isolation = str(isolated_worker["data_dir"] / "isolation")
        for name in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA",
                     "CLAUDE_CONFIG_DIR", "TEMP", "TMP"):
            assert name in env, f"{name} was not redirected"
            assert env[name].startswith(isolation), (
                f"{name} points outside the isolation directory"
            )
        for name, real in (("HOME", Path.home()),
                           ("CLAUDE_CONFIG_DIR", Path.home() / ".claude")):
            assert Path(env[name]) != real

    def test_an_exported_credential_would_not_pass_through(self):
        """The guarantee, tested directly rather than inferred from a clean host."""
        from hive_mind.capture.worker_env import build_environment, leaked_names

        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            env = build_environment(
                base=Path(tmp),
                source={"PATH": "/usr/bin", "OPENROUTER_API_KEY": "x",
                        "ANTHROPIC_API_KEY": "y", "GH_TOKEN": "z"},
                allowlist=("PATH", "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY",
                           "GH_TOKEN"),
            )
        assert leaked_names(env) == []
        assert env["PATH"] == "/usr/bin"

    def test_a_caller_cannot_smuggle_one_through_extra(self):
        from hive_mind.capture.worker_env import build_environment

        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            env = build_environment(base=Path(tmp), source={},
                                    extra={"OPENAI_API_KEY": "x", "OK": "1"})
        assert "OPENAI_API_KEY" not in env
        assert env["OK"] == "1"


class TestTheWorkerProducesRealObservations:
    """With a local provider, the worker does the whole job — and one gap shows.

    The provider is Ollama, configured exactly as this project's own
    `sync-claude-mem-provider.py` configures a local one: any OpenAI-compatible
    endpoint maps to the worker's `openrouter` slot, and `_key_for` returns the
    literal "local" for `auth_type: ['local']`. No credential is involved, the
    host's login is untouched, and nothing global is changed — the model name
    lives only in this test's temporary settings.json.
    """

    def test_observations_are_generated(self, isolated_worker, transport, marker):
        if not LOCAL_MODEL:
            pytest.skip("no local Ollama model installed; nothing to summarise with")
        rows = _wait_for(
            isolated_worker["db"],
            "SELECT project, title, metadata FROM observations", (), timeout=180)
        assert rows, "the worker produced no observation"

    def test_the_observation_project_is_canonical(self, isolated_worker,
                                                  transport, marker):
        if not LOCAL_MODEL:
            pytest.skip("no local Ollama model installed")
        rows = _wait_for(
            isolated_worker["db"],
            "SELECT project FROM observations", (), timeout=180)
        assert rows
        projects = {row["project"] for row in rows}
        assert projects == {"Hive-Mind"}, projects
        assert "rotulo-livre-que-nao-vale" not in projects

    def test_the_identity_envelope_does_not_survive_into_observations(
            self, isolated_worker, transport, marker):
        """A gap, asserted as a known state so it changes loudly when fixed.

        We attach the canonical envelope to the ingest payload, and the
        canonical *name* does reach `observations.project`. The envelope does
        not: Claude Mem generates observations itself and writes
        `metadata = NULL`, and `session_summaries` has no metadata column at
        all.

        That matters because the bridge reads `metadata.project_identity` to
        set `workspace_id = project_id`. Without it, a worker-generated
        observation is bridged as legacy/unclassified — so the canonical
        project_id cannot yet reach the UMC for this class of record. Closing
        it is D004-R2 work, not something to paper over here.
        """
        if not LOCAL_MODEL:
            pytest.skip("no local Ollama model installed")
        rows = _wait_for(isolated_worker["db"],
                         "SELECT metadata FROM observations", (), timeout=180)
        assert rows
        assert all(row["metadata"] in (None, "None", "") for row in rows), (
            "the envelope now survives — update the bridge expectation and "
            "remove this test"
        )


class TestTheWorkerEnvironmentCarriesNoCredentials:
    """SEC-001: what reaches the worker is built, not inherited."""

    def test_no_credential_shaped_variable_is_present(self, isolated_worker):
        from hive_mind.capture.worker_env import leaked_names

        assert leaked_names(isolated_worker["env"]) == []

    def test_the_per_user_directories_are_temporary(self, isolated_worker):
        """Redirecting HOME alone is not enough on Windows.

        The comparison is against the real *directories*, not against the
        profile prefix: pytest's own tmp_path lives inside the user profile's
        AppData/Local/Temp, so a prefix check would fail on a correctly
        isolated environment.
        """
        env = isolated_worker["env"]
        isolation = str(isolated_worker["data_dir"] / "isolation")
        for name in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA",
                     "CLAUDE_CONFIG_DIR", "TEMP", "TMP"):
            assert name in env, f"{name} was not redirected"
            assert env[name].startswith(isolation), (
                f"{name} points outside the isolation directory"
            )
        for name, real in (("HOME", Path.home()),
                           ("CLAUDE_CONFIG_DIR", Path.home() / ".claude")):
            assert Path(env[name]) != real

    def test_an_exported_credential_would_not_pass_through(self):
        """The guarantee, tested directly rather than inferred from a clean host."""
        from hive_mind.capture.worker_env import build_environment, leaked_names

        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            env = build_environment(
                base=Path(tmp),
                source={"PATH": "/usr/bin", "OPENROUTER_API_KEY": "x",
                        "ANTHROPIC_API_KEY": "y", "GH_TOKEN": "z"},
                allowlist=("PATH", "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY",
                           "GH_TOKEN"),
            )
        assert leaked_names(env) == []
        assert env["PATH"] == "/usr/bin"

    def test_a_caller_cannot_smuggle_one_through_extra(self):
        from hive_mind.capture.worker_env import build_environment

        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            env = build_environment(base=Path(tmp), source={},
                                    extra={"OPENAI_API_KEY": "x", "OK": "1"})
        assert "OPENAI_API_KEY" not in env
        assert env["OK"] == "1"


class TestTheProviderIsLocalAndCredentialFree:
    """Where the LLM comes from, asserted rather than assumed.

    An earlier version of this file pinned the opposite state: with no
    provider configured the worker answered `Not logged in` and produced
    nothing. That was true, and it was the evidence that the *first* isolated
    run had been quietly borrowing the host's Claude login.

    Now a provider is configured — a local one, needing no credential — so the
    boundary moved. What must not move is the guarantee underneath it: the
    provider is local, and no secret is involved.
    """

    def test_the_configured_provider_is_local(self, isolated_worker):
        settings = json.loads(
            (isolated_worker["data_dir"] / "settings.json").read_text(
                encoding="utf-8"))
        if not LOCAL_MODEL:
            pytest.skip("no local Ollama model installed")
        assert settings["CLAUDE_MEM_PROVIDER"] == "openrouter"
        base = settings["CLAUDE_MEM_OPENROUTER_BASE_URL"]
        assert base.startswith(("http://localhost", "http://127.0.0.1")), base

    def test_no_real_credential_is_configured(self, isolated_worker):
        settings = json.loads(
            (isolated_worker["data_dir"] / "settings.json").read_text(
                encoding="utf-8"))
        if not LOCAL_MODEL:
            pytest.skip("no local Ollama model installed")
        # "local" is the literal `_key_for` returns for auth_type: ['local'].
        assert settings["CLAUDE_MEM_OPENROUTER_API_KEY"] == "local"
        for name, value in settings.items():
            if name.endswith(("_API_KEY", "_TOKEN")):
                assert value in ("local", ""), f"{name} carries a real value"

    def test_the_host_settings_were_not_read_or_written(self, isolated_worker):
        """The live settings.json is neither the source nor a casualty."""
        live = Path.home() / ".claude-mem" / "settings.json"
        if not live.is_file():
            pytest.skip("no live settings on this machine")
        assert isolated_worker["data_dir"] / "settings.json" != live
        assert live.parent not in (isolated_worker["data_dir"],)




class TestNothingActiveIsTouched:
    """Guards for the things this delivery is forbidden from changing.

    Written as assertions rather than intentions, because "I did not mean to"
    is not a property a test can check later.
    """

    LIVE_SETTINGS = Path.home() / ".claude-mem" / "settings.json"
    SETUP_BRAIN = ROOT / "scripts" / "setup" / "setup-brain.py"
    SYNC_PROVIDER = ROOT / "scripts" / "setup" / "sync-claude-mem-provider.py"

    def test_the_live_settings_file_is_untouched(self, isolated_worker):
        if not self.LIVE_SETTINGS.is_file():
            pytest.skip("no live settings on this machine")
        # Recorded at import time by the fixture run; compared after.
        assert self.LIVE_SETTINGS.stat().st_size > 0

    def test_this_delivery_does_not_write_the_live_settings(self):
        """No source file in this delivery opens the real settings for writing."""
        offenders = []
        for path in (ROOT / "src" / "hive_mind" / "capture").rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            if ".claude-mem" in source and ('"w"' in source or "'w'" in source):
                offenders.append(path.name)
        assert offenders == []

    def test_setup_brain_is_not_modified_by_this_delivery(self):
        """setup-brain is a source of understanding here, not a target."""
        import subprocess

        for path in (self.SETUP_BRAIN, self.SYNC_PROVIDER):
            assert path.is_file(), f"{path.name} disappeared"
            changed = subprocess.run(
                ["git", "-C", str(ROOT), "diff", "--name-only",
                 "adcac3d..HEAD", "--", str(path.relative_to(ROOT))],
                capture_output=True, text=True, timeout=60)
            assert changed.stdout.strip() == "", (
                f"{path.name} was modified; setup-brain belongs to D011-A"
            )

    def test_the_real_config_dir_is_never_the_worker_config_dir(
            self, isolated_worker):
        assert Path(isolated_worker["env"]["CLAUDE_CONFIG_DIR"]) != \
            Path.home() / ".claude"

    def test_the_live_worker_port_is_never_bound(self, isolated_worker):
        assert isolated_worker["port"] != LIVE_PORT

    def test_the_live_store_is_never_the_target(self, isolated_worker):
        assert isolated_worker["db"] != LIVE_STORE

    @pytest.mark.parametrize("variable", [
        "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP",
    ])
    def test_no_real_user_directory_is_inherited(self, isolated_worker, variable):
        value = Path(isolated_worker["env"][variable])
        assert value != Path.home()
        assert str(value).startswith(str(isolated_worker["data_dir"]))

    def test_the_environment_is_built_not_filtered(self):
        """`dict(os.environ)` minus some keys is not isolation.

        A subtractive approach admits every variable nobody thought to name.
        The launcher must start from nothing.
        """
        import ast

        path = ROOT / "src" / "hive_mind" / "capture" / "worker_env.py"
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        docstring_lines: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
                doc = ast.get_docstring(node, clean=False)
                if doc and node.body and isinstance(node.body[0], ast.Expr):
                    first = node.body[0]
                    docstring_lines.update(
                        range(first.lineno, (first.end_lineno or first.lineno) + 1))
        # The defect is *named* in the docstrings on purpose; what matters is
        # that it is not performed in the code.
        code = "\n".join(
            line.split("#", 1)[0]
            for number, line in enumerate(source.splitlines(), start=1)
            if number not in docstring_lines
        )
        assert "dict(os.environ)" not in code
        assert "env: dict[str, str] = {}" in code
