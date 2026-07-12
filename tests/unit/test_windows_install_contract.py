"""Contracts for the canonical native Windows installer entrypoint."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_versioned_profiles_define_their_required_runtime_contracts():
    minimum = (ROOT / "config" / "profiles" / "local-min.env.example").read_text(encoding="utf-8")
    full = (ROOT / "config" / "profiles" / "local-full.env.example").read_text(encoding="utf-8")

    assert "VECTOR_BACKEND=sqlite_vec" in minimum
    assert "MODEL_GATEWAY_MODE=on" in minimum
    assert "VECTOR_BACKEND=milvus" in full
    assert "HIVE_KNOWLEDGE_HEALTH_MILVUS=1" in full
    assert "HIVE_FORCE_LEGACY_LLM=false" in full


def test_npm_windows_flags_map_to_the_canonical_powershell_contract():
    script = """
const init = require('./npm/lib/init');
process.stdout.write(JSON.stringify(init.windowsInstallerArgs({
  profile: 'local-full',
  withTests: true,
  nonInteractive: true,
  installPrerequisites: true,
  dryRun: true,
})));
"""
    result = subprocess.run(
        ["node", "-e", script], cwd=ROOT, text=True, capture_output=True, check=False
    )
    assert result.returncode == 0, result.stderr
    args = json.loads(result.stdout)
    assert args[:5] == ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "install.ps1")]
    assert args[5:] == [
        "-Profile", "local-full", "-WithTests", "-NonInteractive",
        "-InstallPrerequisites", "-DryRun",
    ]


def test_install_powershell_accepts_a_non_mutating_dry_run():
    result = subprocess.run(
        [
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(ROOT / "install.ps1"), "-Profile", "local-min",
            "-InstallPrerequisites", "-DryRun",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Dry-run" in result.stdout

def test_install_rejects_incompatible_repair_and_uninstall_modes():
    result = subprocess.run(
        [
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(ROOT / "install.ps1"), "-DryRun", "-Repair", "-Uninstall",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert "cannot be combined" in result.stderr

def test_install_dry_run_reports_the_selected_versioned_profile():
    result = subprocess.run(
        [
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(ROOT / "install.ps1"), "-Profile", "local-full", "-DryRun",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "config\\profiles\\local-full.env.example" in result.stdout
def test_profile_contract_merges_non_secret_defaults_without_replacing_secrets(tmp_path):
    profile = ROOT / "config" / "profiles" / "local-full.env.example"
    env_path = tmp_path / ".env"
    env_path.write_text(
        "HIVE_MIND_API_KEY=keep-this-secret\nVECTOR_BACKEND=sqlite_vec\nCUSTOM_FLAG=preserve\n",
        encoding="utf-8",
    )
    command = f"""
Import-Module '{ROOT / 'scripts' / 'lib' / 'HiveMind.Windows.psm1'}' -Force -DisableNameChecking
Apply-HiveMindProfileContract -Root '{tmp_path}' -ProfileContract '{profile}'
"""
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    values = dict(
        line.split("=", 1)
        for line in env_path.read_text(encoding="utf-8-sig").splitlines()
        if line and not line.startswith("#")
    )
    assert values["HIVE_MIND_API_KEY"] == "keep-this-secret"
    assert values["CUSTOM_FLAG"] == "preserve"
    assert values["VECTOR_BACKEND"] == "milvus"
    assert values["RAGFLOW_BASE"] == "http://127.0.0.1:9380"


def test_profile_contract_dry_run_does_not_create_or_modify_env(tmp_path):
    profile = ROOT / "config" / "profiles" / "local-min.env.example"
    env_path = tmp_path / ".env"
    env_path.write_text("HIVE_MIND_API_KEY=keep-this-secret\n", encoding="utf-8")
    before = env_path.read_bytes()
    command = f"""
Import-Module '{ROOT / 'scripts' / 'lib' / 'HiveMind.Windows.psm1'}' -Force -DisableNameChecking
Apply-HiveMindProfileContract -Root '{tmp_path}' -ProfileContract '{profile}' -DryRun
"""
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert env_path.read_bytes() == before


def test_windows_npm_init_delegates_instead_of_reimplementing_installation():
    source = (ROOT / "npm" / "lib" / "init.js").read_text(encoding="utf-8")
    start = source.index("function nativeWindowsInit")
    end = source.index("function init(options)", start)
    native = source[start:end]
    assert "powershell.exe" in native
    assert "windowsInstallerArgs(options, dest)" in native
    assert "uv sync" not in native
    assert "mergeMcpConfig" not in native