"""D009-R6 — the whole path, wrapper to config, against temporary state.

The wrapper unit tests use a fake CLI, so they prove forwarding but not that
anything is registered. This runs the real chain:

    register-mcp.{ps1,sh} -> hive-mind agents register -> temporary configs

against realistic config files — JSON with a third-party server already in it,
a Codex `config.toml` with comments, a VS Code file whose root key is
`servers` instead of `mcpServers`, and a prompt file with user content.

Nothing real is touched: HOME, APPDATA and the project root are all temporary,
and the test asserts that the user's actual configs keep their mtime.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PS1 = ROOT / "scripts" / "setup" / "register-mcp.ps1"
SH = ROOT / "scripts" / "setup" / "register-mcp.sh"
BASH = shutil.which("bash")
POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")

WRAPPERS = [
    pytest.param(SH, marks=pytest.mark.skipif(not BASH, reason="no bash")),
    pytest.param(PS1, marks=pytest.mark.skipif(not POWERSHELL, reason="no powershell")),
]

THIRD_PARTY = {"command": "somebody-elses-server", "args": ["--keep-me"]}


@pytest.fixture
def sandbox(tmp_path):
    """A temporary HOME/APPDATA/project root with realistic existing configs."""
    home = tmp_path / "home"
    appdata = tmp_path / "appdata"
    project = tmp_path / "project"
    for d in (home, appdata, project):
        d.mkdir(parents=True)

    # A JSON config that already has someone else's MCP server in it.
    qwen = home / ".qwen" / "settings.json"
    qwen.parent.mkdir(parents=True)
    qwen.write_text(json.dumps({"mcpServers": {"other": THIRD_PARTY},
                                "theme": "dark"}, indent=2), encoding="utf-8")

    # A Codex TOML with comments and a third-party entry.
    codex = home / ".codex" / "config.toml"
    codex.parent.mkdir(parents=True)
    codex.write_text(
        "# my codex config\nmodel = \"gpt-5\"\n\n"
        "[mcp_servers.keep-me]\ncommand = \"x\"\n",
        encoding="utf-8")

    # VS Code uses `servers`, not `mcpServers`.
    vscode = project / ".vscode" / "mcp.json"
    vscode.parent.mkdir(parents=True)
    vscode.write_text(json.dumps({"servers": {"other": THIRD_PARTY}}, indent=2),
                      encoding="utf-8")

    # A prompt file with content the user wrote.
    (project / "AGENTS.md").write_text("# My notes\n\nkeep this line\n",
                                       encoding="utf-8")
    # The instruction source the CLI reads.
    (project / "config").mkdir()
    (project / "config" / "sinapse-agent-prompt.md").write_text(
        "Follow the Hive-Mind protocol.\n", encoding="utf-8")

    return {"home": home, "appdata": appdata, "project": project,
            "qwen": qwen, "codex": codex, "vscode": vscode}


def _invoke(wrapper: Path, args: list[str], sandbox) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["USERPROFILE"] = str(sandbox["home"])
    env["HOME"] = str(sandbox["home"])
    env["APPDATA"] = str(sandbox["appdata"])
    # PROJECT_ROOT points the wrapper's venv lookup at the sandbox; the real
    # `hive-mind` is on PATH via `uv run`, so the lookup never fires.
    env["PROJECT_ROOT"] = str(ROOT)
    args = [*args, "--project-root", str(sandbox["project"])]

    if wrapper.suffix == ".sh":
        command = [BASH, str(wrapper), *args]
    else:
        command = [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass",
                   "-File", str(wrapper), *args]
    return subprocess.run(command, capture_output=True, text=True, env=env,
                          encoding="utf-8", errors="replace", timeout=300,
                          cwd=str(ROOT))


@pytest.fixture(autouse=True)
def hive_mind_on_path(monkeypatch):
    """Put the project's own console script ahead of anything else."""
    scripts = Path(sys.executable).parent
    monkeypatch.setenv("PATH", f"{scripts}{os.pathsep}{os.environ['PATH']}")
    if not (scripts / "hive-mind.exe").exists() and not (scripts / "hive-mind").exists():
        pytest.skip("hive-mind console script not installed in this environment")


@pytest.mark.parametrize("wrapper", WRAPPERS)
class TestRegistrationThroughTheWrapper:
    def test_dry_run_writes_nothing(self, wrapper, sandbox):
        before = sandbox["qwen"].read_text(encoding="utf-8")
        proc = _invoke(wrapper, ["--only", "qwen"], sandbox)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert sandbox["qwen"].read_text(encoding="utf-8") == before

    def test_apply_registers_and_keeps_third_parties(self, wrapper, sandbox):
        proc = _invoke(wrapper, ["--only", "qwen", "--apply"], sandbox)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        data = json.loads(sandbox["qwen"].read_text(encoding="utf-8"))
        assert "sinapse-memory" in data["mcpServers"]
        assert set(data["mcpServers"]) == {"other", "sinapse-memory"}, (
            "only the orchestrator is exposed; the federated raw backends "
            "(claude-mem-local, neural-memory-local) must not reappear"
        )
        assert data["mcpServers"]["other"] == THIRD_PARTY
        assert data["theme"] == "dark", "unrelated keys must survive"

    def test_a_second_apply_changes_nothing(self, wrapper, sandbox):
        _invoke(wrapper, ["--only", "qwen", "--apply"], sandbox)
        first = sandbox["qwen"].read_text(encoding="utf-8")
        _invoke(wrapper, ["--only", "qwen", "--apply"], sandbox)
        assert sandbox["qwen"].read_text(encoding="utf-8") == first

    def test_a_backup_is_left_behind(self, wrapper, sandbox):
        _invoke(wrapper, ["--only", "qwen", "--apply"], sandbox)
        backups = list(sandbox["qwen"].parent.glob("*.hive-bak*"))
        assert backups, "an existing config must be backed up before rewriting"
        original = json.loads(backups[0].read_text(encoding="utf-8"))
        assert "sinapse-memory" not in original["mcpServers"]

    def test_toml_stays_valid_and_keeps_its_neighbours(self, wrapper, sandbox):
        import tomlkit

        proc = _invoke(wrapper, ["--only", "codex", "--apply"], sandbox)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        doc = tomlkit.parse(sandbox["codex"].read_text(encoding="utf-8"))
        assert "sinapse-memory" in doc["mcp_servers"]
        assert "keep-me" in doc["mcp_servers"]
        assert doc["model"] == "gpt-5"
        assert "# my codex config" in sandbox["codex"].read_text(encoding="utf-8")

    def test_vscode_root_key_is_respected(self, wrapper, sandbox):
        proc = _invoke(wrapper, ["--only", "vscode", "--apply"], sandbox)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        data = json.loads(sandbox["vscode"].read_text(encoding="utf-8"))
        assert "sinapse-memory" in data["servers"]
        assert data["servers"]["sinapse-memory"]["type"] == "stdio", (
            "VS Code entries carry an explicit transport type; the legacy "
            "script set it and the native path must not quietly drop it"
        )
        assert "mcpServers" not in data, "must not invent a second root key"

    def test_instructions_are_installed_on_request(self, wrapper, sandbox):
        proc = _invoke(wrapper, ["--only", "codex", "--apply", "--instructions"],
                       sandbox)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        text = (sandbox["project"] / "AGENTS.md").read_text(encoding="utf-8")
        assert "Follow the Hive-Mind protocol." in text
        assert "keep this line" in text, "user content must survive"

    def test_no_instructions_leaves_the_prompt_alone(self, wrapper, sandbox):
        before = (sandbox["project"] / "AGENTS.md").read_text(encoding="utf-8")
        _invoke(wrapper, ["--only", "codex", "--apply", "--no-instructions"], sandbox)
        assert (sandbox["project"] / "AGENTS.md").read_text(encoding="utf-8") == before

    def test_an_unknown_agent_exits_two(self, wrapper, sandbox):
        """The legacy contract callers branch on."""
        proc = _invoke(wrapper, ["--only", "not-an-agent"], sandbox)
        assert proc.returncode == 2

    def test_list_names_the_agents(self, wrapper, sandbox):
        proc = _invoke(wrapper, ["--list"], sandbox)
        assert proc.returncode == 0
        assert "codex" in proc.stdout and "swarmclaw" in proc.stdout


@pytest.mark.parametrize("wrapper", WRAPPERS)
def test_unregister_removes_only_hive_mind(wrapper, sandbox):
    """Rollback: what register added, unregister takes back — and nothing else."""
    _invoke(wrapper, ["--only", "qwen", "--apply"], sandbox)
    env = dict(os.environ)
    env.update({"USERPROFILE": str(sandbox["home"]), "HOME": str(sandbox["home"]),
                "APPDATA": str(sandbox["appdata"])})
    subprocess.run(
        [sys.executable, "-m", "hive_mind.cli", "agents", "unregister",
         "--only", "qwen", "--apply", "--project-root", str(sandbox["project"])],
        capture_output=True, text=True, env=env, timeout=300, cwd=str(ROOT), check=True,
    )
    data = json.loads(sandbox["qwen"].read_text(encoding="utf-8"))
    assert "sinapse-memory" not in data["mcpServers"]
    assert data["mcpServers"]["other"] == THIRD_PARTY
    assert data["theme"] == "dark"


def test_the_real_user_configs_were_never_touched(sandbox):
    """The whole suite runs in a sandbox; this states it as an assertion.

    Named explicitly because the delivery brief forbids writing to
    ~/.codex/config.toml, ~/.claude.json, ~/.qwen and the real APPDATA.
    """
    real_home = Path(os.path.expanduser("~"))
    watched = [real_home / ".codex" / "config.toml", real_home / ".claude.json",
               real_home / ".qwen" / "settings.json"]
    before = {p: p.stat().st_mtime_ns for p in watched if p.exists()}
    if BASH:
        _invoke(SH, ["--only", "qwen", "--apply"], sandbox)
    if POWERSHELL:
        _invoke(PS1, ["--only", "codex", "--apply"], sandbox)
    after = {p: p.stat().st_mtime_ns for p in watched if p.exists()}
    assert before == after, "a real user config was modified"
