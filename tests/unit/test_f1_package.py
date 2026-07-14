"""F1 contract tests: entry points, version, help.

Covers items from F1 Secao 7 of the F1 approval:
- entry points;
- versao sem mudanca;
- help.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"


def _env():
    return {
        "PYTHONPATH": str(SRC),
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
    }


def _run_module(module, *args):
    return subprocess.run(
        [sys.executable, "-m", module, *args],
        capture_output=True,
        text=True,
        env=_env(),
        cwd=str(REPO),
        check=False,
    )


def test_cli_version_returns_zero():
    r = _run_module("hive_mind.cli", "--version")
    assert r.returncode == 0, r.stderr
    assert r.stdout.startswith("hive-mind ")
    assert r.stdout.strip() == "hive-mind 0.0.0+f1"


def test_daemon_version_returns_zero():
    r = _run_module("hive_mind.daemon.main", "--version")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "hive-mindd 0.0.0+f1"


def test_cli_help_returns_zero_and_lists_project_root():
    r = _run_module("hive_mind.cli", "--help")
    assert r.returncode == 0, r.stderr
    assert "project-root" in r.stdout
    assert "--version" in r.stdout


def test_daemon_help_returns_zero_and_lists_run():
    r = _run_module("hive_mind.daemon.main", "--help")
    assert r.returncode == 0, r.stderr
    assert "run" in r.stdout


def test_daemon_run_stub_prints_marker_and_exits_zero():
    r = _run_module("hive_mind.daemon.main", "run")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "not implemented in F1"


def test_package_version_is_not_project_version():
    """F1 explicitly forbids bumping the project version (3.10.1)."""
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.M)
    assert m is not None, "pyproject.toml missing version"
    assert m.group(1) == "3.10.1"


def test_no_subprocess_spawned_by_daemon_run():
    """The F1 daemon run stub must not call subprocess.Popen.

    Runs the daemon module in a clean subprocess with PYTHONPATH set
    to the src/ tree and a spy in place. The spy is installed by
    wrapping the daemon main() with a sitecustomize-style import
    shim: a tiny helper script (``_f1_popen_spy.py``) is written to
    ``tmp_path`` and put first on PYTHONPATH, so it patches
    ``subprocess.Popen`` before the daemon module is imported.
    """
    import subprocess as sp
    import sys as _sys
    import textwrap
    from pathlib import Path as _P

    spy = _P(_sys.exec_prefix)  # not used; placeholder

    # We rely on the subprocess run output: the daemon prints exactly
    # "not implemented in F1" and exits 0. We then re-run the daemon
    # under a tmp interpreter with a sitecustomize that patches
    # Popen, and we assert that the patch reports zero Popen calls.
    tmp = _P(_sys.executable).parent
    # Inline a tiny Python script that imports the daemon, monkey-
    # patches Popen, calls main(["run"]), and prints the call count.
    helper = textwrap.dedent(
        """
        import sys, subprocess
        calls = []
        real = subprocess.Popen
        def spy(*a, **kw):
            calls.append((a, kw))
            return real(*a, **kw)
        subprocess.Popen = spy
        import hive_mind.daemon.main as dmain
        rc = dmain.main(["run"])
        subprocess.Popen = real
        print("CALLS=" + str(len(calls)))
        sys.exit(rc)
        """
    ).strip()
    r = sp.run(
        [_sys.executable, "-c", helper],
        capture_output=True,
        text=True,
        env={"PYTHONPATH": str(SRC), "PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        cwd=str(REPO),
        check=False,
    )
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "not implemented in F1" + chr(10) + "CALLS=0" or r.stdout.strip().endswith("CALLS=0")
    assert "not implemented in F1" in r.stdout
    assert r.stdout.rstrip().endswith("CALLS=0")


def test_daemon_run_is_noop_in_subprocess():
    r = _run_module("hive_mind.daemon.main", "run")
    assert r.returncode == 0
    assert r.stdout.strip() == "not implemented in F1"
    assert r.stderr == ""
