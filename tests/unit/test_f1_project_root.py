"""F1 contract tests: project root resolution (D.5).

Covers items from F1 Secao 7:
- project root explicito;
- HIVE_MIND_HOME;
- config persistida;
- descoberta ascendente;
- execucao fora do root;
- path Windows com espacos;
- path Unicode;
- root inexistente;
- marcadores incompletos;
- nenhuma inicializacao de servico.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"

PYPROJECT = "[project]" + chr(10) + "name=x" + chr(10)
AGENTS = "# agents" + chr(10)


def _isolated_env(tmp_path=None):
    """Build a clean env with the bare minimum the CLI needs."""
    e = {
        "PYTHONPATH": str(SRC),
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\Windows"),
        "TEMP": str(tmp_path) if tmp_path else os.environ.get("TEMP", ""),
        "TMP": str(tmp_path) if tmp_path else os.environ.get("TMP", ""),
    }
    if sys.platform == "win32":
        e["USERPROFILE"] = str(tmp_path) if tmp_path else os.environ.get("USERPROFILE", "")
        e["APPDATA"] = str((tmp_path / "AppData" / "Roaming")) if tmp_path else os.environ.get("APPDATA", "")
        e["HOMEDRIVE"] = os.environ.get("HOMEDRIVE", "C:")
        e["HOMEPATH"] = os.environ.get("HOMEPATH", "\\Users\\miche")
    else:
        e["HOME"] = str(tmp_path) if tmp_path else os.environ.get("HOME", "")
        e["XDG_CONFIG_HOME"] = str(tmp_path) if tmp_path else os.environ.get("XDG_CONFIG_HOME", "")
    return e


def _run_cli(*args, env_extra=None, cwd=None, tmp_path=None):
    e = _isolated_env(tmp_path=tmp_path)
    if env_extra:
        e.update(env_extra)
    return subprocess.run(
        [sys.executable, "-m", "hive_mind.cli", *args],
        capture_output=True,
        text=True,
        env=e,
        cwd=str(cwd) if cwd is not None else str(REPO),
        check=False,
    )


def test_explicit_project_root():
    r = _run_cli("project-root", "--project-root", str(REPO))
    assert r.returncode == 0, r.stderr
    assert Path(r.stdout.strip()).resolve() == REPO.resolve()


def test_hive_mind_home_env():
    r = _run_cli("project-root", env_extra={"HIVE_MIND_HOME": str(REPO)})
    assert r.returncode == 0, r.stderr
    assert Path(r.stdout.strip()).resolve() == REPO.resolve()


def test_persisted_config(tmp_path):
    cfg_root = tmp_path / "AppData" / "Roaming" / "Hive-Mind"
    cfg_root.mkdir(parents=True, exist_ok=True)
    (cfg_root / "project-root").write_text(str(REPO), encoding="utf-8")
    e = {
        "APPDATA": str(cfg_root.parent.parent),
        "XDG_CONFIG_HOME": str(tmp_path),
        "USERPROFILE": str(tmp_path),
        "HOME": str(tmp_path),
    }
    r = _run_cli("project-root", env_extra=e, tmp_path=tmp_path)
    assert r.returncode == 0, r.stderr
    assert Path(r.stdout.strip()).resolve() == REPO.resolve()


def test_upward_search_finds_repo():
    r = _run_cli("project-root", cwd=REPO / "scripts")
    assert r.returncode == 0, r.stderr
    assert Path(r.stdout.strip()).resolve() == REPO.resolve()


def test_outside_repo_with_no_markers_fails(tmp_path):
    r = _run_cli("project-root", cwd=tmp_path, tmp_path=tmp_path)
    assert r.returncode == 78
    assert "could not resolve project root" in r.stderr


def test_nonexistent_root_fails(tmp_path):
    bogus = tmp_path / "does-not-exist-12345"
    r = _run_cli("project-root", "--project-root", str(bogus), tmp_path=tmp_path)
    assert r.returncode != 0


def test_incomplete_markers_rejected(tmp_path):
    """A single isolated marker must not be enough; need 2 of 3."""
    upward = tmp_path / "isolated"
    upward.mkdir()
    (upward / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    r = _run_cli("project-root", cwd=upward, tmp_path=tmp_path)
    assert r.returncode == 78


def test_windows_path_with_spaces(tmp_path):
    if sys.platform != "win32":
        pytest.skip("Windows path with spaces only testable on win32")
    spaced = tmp_path / "Program Files" / "Hive Mind"
    spaced.mkdir(parents=True)
    (spaced / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    (spaced / "AGENTS.md").write_text(AGENTS, encoding="utf-8")
    r = _run_cli("project-root", "--project-root", str(spaced), tmp_path=tmp_path)
    assert r.returncode == 0, r.stderr
    assert Path(r.stdout.strip()).resolve() == spaced.resolve()


def test_unicode_path(tmp_path):
    unicode_dir = tmp_path / "memoria"
    unicode_dir.mkdir()
    (unicode_dir / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    (unicode_dir / "AGENTS.md").write_text(AGENTS, encoding="utf-8")
    r = _run_cli("project-root", "--project-root", str(unicode_dir), tmp_path=tmp_path)
    assert r.returncode == 0, r.stderr
    assert Path(r.stdout.strip()).resolve() == unicode_dir.resolve()


def test_no_service_started_in_daemon_run():
    r = subprocess.run(
        [sys.executable, "-m", "hive_mind.daemon.main", "run"],
        capture_output=True,
        text=True,
        env={"PYTHONPATH": str(SRC), "PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        cwd=str(REPO),
        check=False,
    )
    assert r.returncode == 69
    assert 'not implemented in F1' in r.stderr
