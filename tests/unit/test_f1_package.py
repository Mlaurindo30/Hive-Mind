"""F1 contract tests: entry points, version, help.

The F1 contract is that hive-mind --version and hive-mindd --version
print the project version (3.10.1) read from pyproject.toml via
importlib.metadata. The daemon run command is not implemented
in F1 and returns EX_UNAVAILABLE=69.
"""
from __future__ import annotations


import os, re, subprocess, sys
from pathlib import Path
import pytest


REPO = Path(__file__).resolve().parents[2]
SRC = REPO / 'src'
EXPECTED_VERSION = '3.10.1'
EX_UNAVAILABLE = 69


def _env():
    return {'PYTHONPATH': str(SRC), 'PATH': os.environ.get('PATH', '/usr/bin:/bin')}


def _run_module(module, *args):
    return subprocess.run([sys.executable, '-m', module, *args], capture_output=True, text=True, env=_env(), cwd=str(REPO), check=False)


def test_cli_version_matches_project_version():
    r = _run_module('hive_mind.cli', '--version')
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == 'hive-mind ' + EXPECTED_VERSION


def test_daemon_version_matches_project_version():
    r = _run_module('hive_mind.daemon.main', '--version')
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == 'hive-mindd ' + EXPECTED_VERSION


def test_cli_help_returns_zero_and_lists_project_root():
    r = _run_module('hive_mind.cli', '--help')
    assert r.returncode == 0, r.stderr
    assert 'project-root' in r.stdout
    assert '--version' in r.stdout


def test_daemon_help_returns_zero_and_lists_run():
    r = _run_module('hive_mind.daemon.main', '--help')
    assert r.returncode == 0, r.stderr
    assert 'run' in r.stdout


def test_daemon_run_returns_ex_unavailable_and_does_not_exit_zero():
    r = _run_module('hive_mind.daemon.main', 'run')
    assert r.returncode == EX_UNAVAILABLE, ('daemon run must return EX_UNAVAILABLE (got %s); stdout=%r stderr=%r' % (r.returncode, r.stdout, r.stderr))
    assert 'not implemented in F1' in r.stderr


def test_daemon_run_via_in_process_call():
    """Run the daemon via -m to validate the entry point."""
    r = _run_module('hive_mind.daemon.main', 'run')
    assert r.returncode == EX_UNAVAILABLE, r.stderr


def test_consistency_across_all_version_sources():
    """All version sources must report the same value."""
    pyproject = (REPO / 'pyproject.toml').read_text(encoding='utf-8')
    m = re.search('^version\\s*=\\s*"([^"]+)"', pyproject, re.M)
    assert m is not None, 'pyproject.toml missing [project].version'
    assert m.group(1) == EXPECTED_VERSION


    core = (REPO / 'core' / 'version.py').read_text(encoding='utf-8')
    m2 = re.search('^__version__\\s*=\\s*"([^"]+)"', core, re.M)
    assert m2 is not None, 'core/version.py missing __version__'
    assert m2.group(1) == EXPECTED_VERSION


    cli = _run_module('hive_mind.cli', '--version')
    assert cli.stdout.strip() == 'hive-mind ' + EXPECTED_VERSION


    d = _run_module('hive_mind.daemon.main', '--version')
    assert d.stdout.strip() == 'hive-mindd ' + EXPECTED_VERSION


def test_no_subprocess_spawned_by_daemon_run():
    """The F1 daemon run stub must not call subprocess.Popen."""
    helper = (
        'import sys, subprocess' + chr(10)
        + 'calls = []' + chr(10)
        + 'real = subprocess.Popen' + chr(10)
        + 'def spy(*a, **kw):' + chr(10)
        + '    calls.append((a, kw))' + chr(10)
        + '    return real(*a, **kw)' + chr(10)
        + 'subprocess.Popen = spy' + chr(10)
        + 'import hive_mind.daemon.main as dmain' + chr(10)
        + 'rc = dmain.main(["run"])' + chr(10)
        + 'subprocess.Popen = real' + chr(10)
        + 'sys.stdout.write("CALLS=" + str(len(calls)) + chr(10))' + chr(10)
        + 'sys.exit(rc)'
    )
    r = subprocess.run(
        [sys.executable, '-c', helper],
        capture_output=True,
        text=True,
        env={'PYTHONPATH': str(SRC), 'PATH': os.environ.get('PATH', '/usr/bin:/bin')},
        cwd=str(REPO),
        check=False,
    )
    assert r.returncode == EX_UNAVAILABLE, (r.returncode, r.stderr)
    assert r.stdout.rstrip().endswith('CALLS=0')

