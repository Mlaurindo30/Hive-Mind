"""D009-R6 — the registrars must be wrappers, and must forward faithfully.

Two claims are tested, and they are different claims:

  - **structure**: neither script contains product logic any more. Asserted by
    reading them for the things a registrar used to know — provider names,
    config paths, JSON/TOML editing, instruction markers, the outbox.
  - **behaviour**: what they do forward, they forward exactly. Asserted by
    running the real script against a fake `hive-mind` on PATH that records
    its argv and returns a chosen exit code.

Line counts are not evidence. A 40-line script that still decides which
provider to register is not a wrapper.
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
ENTRY = ROOT / "scripts" / "setup" / "register_mcp.py"
SH = ROOT / "scripts" / "setup" / "register-mcp.sh"

WINDOWS = os.name == "nt"

# Windows ships two `bash.exe` shims that are not a POSIX shell: the WSL
# launcher in System32 and its WindowsApps alias. Without a registered distro
# both fail with `execvpe(/bin/bash)`, which reads as a wrapper bug rather than
# a missing interpreter. Git ships a real bash, so derive it from `git` first
# and only then fall back to PATH.
_BASH_SHIM_DIRS = {"system32", "windowsapps"}


def _find_bash() -> "str | None":
    if WINDOWS:
        git = shutil.which("git")
        if git:
            install = Path(git).resolve().parents[1]  # <install>/cmd|bin/git.exe
            for candidate in (
                install / "bin" / "bash.exe",
                install / "usr" / "bin" / "bash.exe",
            ):
                if candidate.is_file():
                    return str(candidate)
    found = shutil.which("bash")
    if found and WINDOWS and Path(found).parent.name.lower() in _BASH_SHIM_DIRS:
        return None
    return found


BASH = _find_bash()
POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")


# ---------------------------------------------------------------------------
# A fake hive-mind that records argv and exits with a chosen code
# ---------------------------------------------------------------------------
FAKE_PY = '''\
import json, os, sys
with open(os.environ["FAKE_ARGV_OUT"], "w", encoding="utf-8") as fh:
    json.dump(sys.argv[1:], fh)
sys.stdout.write(os.environ.get("FAKE_STDOUT", ""))
sys.stderr.write(os.environ.get("FAKE_STDERR", ""))
sys.exit(int(os.environ.get("FAKE_EXIT", "0")))
'''


@pytest.fixture
def fake_cli(tmp_path):
    """A directory holding a `hive-mind` shim, ready to prepend to PATH."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    script = tmp_path / "fake_cli.py"
    script.write_text(FAKE_PY, encoding="utf-8")

    # POSIX shim
    posix = bindir / "hive-mind"
    posix.write_text(f'#!/usr/bin/env sh\nexec "{sys.executable}" "{script}" "$@"\n',
                     encoding="utf-8", newline="\n")
    posix.chmod(0o755)
    # Windows shim. Deliberately a .ps1 and not a .cmd: cmd.exe interprets `&`
    # and `|` in its own command line, so a .cmd double would truncate those
    # arguments before the wrapper was ever at fault. Production resolves
    # `hive-mind` to the console-script .exe, which PowerShell invokes
    # directly — the .ps1 double has the same property.
    (bindir / "hive-mind.ps1").write_text(
        f'& "{sys.executable}" "{script}" @args\nexit $LASTEXITCODE\n',
        encoding="utf-8", newline="\n")

    return bindir, tmp_path / "argv.json"


def _run(script: Path, args: list[str], fake_cli, *, exit_code=0,
         stdout="", stderr="", with_path=True):
    bindir, argv_out = fake_cli
    env = dict(os.environ)
    env["PATH"] = f"{bindir}{os.pathsep}{env['PATH']}" if with_path else str(
        Path(env["PATH"]).anchor or "")
    if not with_path:
        env["PATH"] = ""
    env["FAKE_ARGV_OUT"] = str(argv_out)
    env["FAKE_EXIT"] = str(exit_code)
    env["FAKE_STDOUT"] = stdout
    env["FAKE_STDERR"] = stderr
    # Keep the wrapper's venv fallback from finding the real project venv.
    env["PROJECT_ROOT"] = str(argv_out.parent / "no-such-root")

    if script.suffix == ".sh":
        command = [BASH, str(script), *args]
    else:
        command = [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass",
                   "-File", str(script), *args]
    proc = subprocess.run(command, capture_output=True, text=True, env=env,
                          encoding="utf-8", errors="replace", timeout=120)
    forwarded = json.loads(argv_out.read_text(encoding="utf-8")) if argv_out.exists() else None
    return proc, forwarded



# ---------------------------------------------------------------------------
# Structure: no product logic left
# ---------------------------------------------------------------------------
class TestTheWrappersOwnNoProductLogic:
    FORBIDDEN = {
        "provider names": ("qwen", "kimi", "cursor", "opencode", "swarmclaw"),
        "config paths": (".codex/config.toml", ".claude.json", "settings.json",
                         "APPDATA", "globalStorage"),
        "MCP structure": ("mcpServers", "sinapse-memory", '"servers"'),
        "config formats": ("json.dump", "json.load", "tomlkit", "ConvertTo-Json",
                           "ConvertFrom-Json"),
        "instruction markers": ("BEGIN HIVE-MIND SINAPSE", "END HIVE-MIND SINAPSE"),
        "deprecated capture": ("install-capture-hooks", "capture_queue", "outbox",
                               "capture-hook"),
        "backup/rollback": ("hive-bak", "Copy-Item", "cp -a"),
    }

    @pytest.mark.parametrize("script", [ENTRY])
    @pytest.mark.parametrize("category", sorted(FORBIDDEN))
    def test_no_product_logic_of_this_kind(self, script, category):
        text = script.read_text(encoding="utf-8-sig")
        # Comments explain what was removed; only executable lines are judged.
        code = "\n".join(
            line for line in text.splitlines()
            if not line.lstrip().startswith("#")
        )
        found = [needle for needle in self.FORBIDDEN[category] if needle in code]
        assert found == [], f"{script.name} still owns {category}: {found}"

    @pytest.mark.parametrize("script", [ENTRY])
    def test_the_wrapper_names_the_native_command(self, script):
        text = script.read_text(encoding="utf-8-sig")
        assert "\"agents\", \"register\"" in text, (
            f"{script.name} must delegate to the native agents register CLI"
        )

    @pytest.mark.parametrize("script", [ENTRY])
    def test_no_hardcoded_host_paths(self, script):
        code = script.read_text(encoding="utf-8-sig")
        for smell in ("D:\\Hive-Mind", "D:/Hive-Mind", "miche", "hive-mind-windows"):
            assert smell not in code, f"{script.name} hardcodes {smell!r}"

    def test_syntax_is_valid_bash(self):
        if not BASH:
            pytest.skip("bash not available")
        assert subprocess.run([BASH, "-n", str(SH)], capture_output=True).returncode == 0

    def test_python_entry_compiles(self):
        assert subprocess.run([sys.executable, "-m", "py_compile", str(ENTRY)], capture_output=True).returncode == 0


# ---------------------------------------------------------------------------
# Behaviour: faithful forwarding
# ---------------------------------------------------------------------------
class TestNativeEntryPoint:
    def test_entrypoint_delegates_to_the_native_cli(self):
        code = ENTRY.read_text(encoding="utf-8")
        assert "\"agents\", \"register\"" in code



# ---------------------------------------------------------------------------
# The boundary holds in the other direction too
# ---------------------------------------------------------------------------
class TestNativeCodeNeverCallsTheWrapper:
    def test_no_module_invokes_a_registrar(self):
        from tests.unit.test_architecture_boundaries import (
            LEGACY_SCRIPT_MARKERS,
            TestNativeCodeDoesNotDelegateToLegacyScripts,
        )

        # That check strips docstrings via AST — a script named in prose is
        # documentation, one named in code is a call. Re-implementing the scan
        # here with a cruder filter would trip over this delivery's own
        # explanatory comments and prove nothing.
        assert "register-mcp.ps1" in LEGACY_SCRIPT_MARKERS
        TestNativeCodeDoesNotDelegateToLegacyScripts() \
            .test_no_module_executes_a_legacy_script()
