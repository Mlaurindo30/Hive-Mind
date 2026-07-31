"""Contracts for the canonical native Windows installer entrypoint."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from core.auth import HIVE_LLM_ROLES
from hive_mind.install.fullstack_readiness import test_tcp_readiness as tcp_readiness_probe
from hive_mind.install.windows_prereqs import invoke_prerequisite_bootstrap
from hive_mind.install.windows_launchers import expected_gui_launchers
from hive_mind.maintenance.windows_runtime import windows_runtime_specs
from hive_mind.validation.runtime_paths import (
    RuntimePathReference,
    find_runtime_path_violations,
)


ROOT = Path(__file__).resolve().parents[2]
NATIVE_INSTALL = ROOT / "src" / "hive_mind" / "install" / "windows.py"


def test_versioned_profiles_define_their_required_runtime_contracts():
    minimum = (ROOT / "config" / "profiles" / "local-min.env.example").read_text(encoding="utf-8")
    full = (ROOT / "config" / "profiles" / "local-full.env.example").read_text(encoding="utf-8")

    assert "VECTOR_BACKEND=sqlite_vec" in minimum
    assert "MODEL_GATEWAY_MODE=on" in minimum
    assert "VECTOR_BACKEND=milvus" in full
    assert "HIVE_KNOWLEDGE_HEALTH_MILVUS=1" in full
    assert "HIVE_FORCE_LEGACY_LLM=false" in full
    for role in ("VALIDATOR", "ROUTER", "DISTILLER"):
        assert f"HIVE_{role}_PROVIDER=ollama" in full
        assert f"HIVE_{role}_MODEL=qwen2.5:3b" in full
        assert role.lower() in HIVE_LLM_ROLES
    assert "HIVE_GRAPHITI_PROVIDER=ollama" in full
    assert "HIVE_GRAPHITI_MODEL=granite4.1:8b" in full


def test_fullstack_tcp_probe_is_owned_by_native_python():
    assert tcp_readiness_probe("127.0.0.1", 1) is False


def test_fullstack_readiness_is_owned_by_native_python():
    source = (ROOT / "src" / "hive_mind" / "install" / "fullstack_readiness.py").read_text(encoding="utf-8")

    assert "def test_tcp_readiness" in source
    assert "def test_fullstack_readiness" in source
    assert "docker info" not in source
    assert "Invoke-WebRequest" not in source


def test_bootstrap_prerequisites_is_owned_by_native_python():
    source = (ROOT / "src" / "hive_mind" / "install" / "windows_prereqs.py").read_text(encoding="utf-8")
    report = invoke_prerequisite_bootstrap(root=ROOT, profile="local-min", dry_run=True)

    assert "def invoke_prerequisite_bootstrap" in source
    assert "winget" in source
    assert report.restart_required is False

def test_npm_windows_flags_map_to_the_canonical_python_contract():
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
    assert args == [
        str(ROOT / "scripts" / "setup" / "windows_install_entry.py"),
        "--root", str(ROOT), "--profile", "local-full", "--with-tests",
        "--non-interactive", "--install-prerequisites", "--dry-run",
    ]


def _windows_install(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(ROOT / ".venv" / "Scripts" / "python.exe"), str(ROOT / "scripts" / "setup" / "windows_install_entry.py"), *args],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )


def test_install_python_entry_accepts_a_non_mutating_dry_run():
    result = _windows_install("--profile", "local-min", "--install-prerequisites", "--dry-run")
    assert result.returncode == 0, result.stderr
    assert "Dry-run" in result.stdout


def test_install_rejects_incompatible_repair_and_uninstall_modes():
    result = _windows_install("--dry-run", "--repair", "--uninstall")
    assert result.returncode != 0
    assert "cannot be combined" in (result.stderr + result.stdout)


def test_install_dry_run_reports_the_selected_versioned_profile():
    result = _windows_install("--profile", "local-full", "--dry-run")
    assert result.returncode == 0, result.stderr
    assert "config\\profiles\\local-full.env.example" in result.stdout


def test_native_windows_install_uses_the_python_prerequisite_owner():
    source = NATIVE_INSTALL.read_text(encoding="utf-8")

    assert "invoke_prerequisite_bootstrap" in source
    assert "bootstrap-prerequisites.ps1" not in source


def test_packaging_contract_does_not_pin_local_integrations_to_editable_paths():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    lockfile = (ROOT / "uv.lock").read_text(encoding="utf-8")

    assert 'graphifyy = { path = "integrations/graphify"' not in pyproject
    assert 'neural-memory = { path = "integrations/neural-memory"' not in pyproject
    assert 'editable = "integrations/graphify"' not in lockfile
    assert 'editable = "integrations/neural-memory"' not in lockfile
    assert 'source = { editable = "integrations/graphify" }' not in lockfile
    assert 'source = { editable = "integrations/neural-memory" }' not in lockfile
    assert 'https://files.pythonhosted.org' in lockfile


def test_install_bat_delegates_to_the_python_entrypoint():
    source = (ROOT / "install.bat").read_text(encoding="utf-8")

    assert "windows_install_entry.py" in source
    assert ".venv\\Scripts\\python.exe" in source
    assert "powershell.exe" not in source.lower()

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
    assert "powershell.exe" not in native
    assert "py.exe" in native
    assert "windowsInstallerArgs(options, dest)" in native
    assert "uv sync" not in native
    assert "mergeMcpConfig" not in native

def test_windows_autostart_contract_is_versioned():
    native = (ROOT / "src" / "hive_mind" / "maintenance" / "windows_runtime.py").read_text(encoding="utf-8")
    assert "HiveMind-Supervisor" in native
    assert "hive-mind-post-rebootw" in native
    assert "hive-mind-supervisorw" in native
    assert "expected_gui_launchers" in native
    assert "start-windows-supervisor-hidden.vbs" not in native
    assert "powershell.exe" not in native


def test_windows_autostart_contract_rejects_legacy_wrappers_for_protected_tasks():
    source = (ROOT / "src" / "hive_mind" / "maintenance" / "windows_runtime.py").read_text(encoding="utf-8")

    assert "validate_gui_launchers(root)" in source
    assert ".backup.xml" in source
    assert "failed to restore" in source
    assert "start-windows-supervisor-hidden.vbs" not in source
    assert "_legacy_supervisor_wrapper_compatible" not in source
    assert "_install_startup_watchdog" not in source
    assert "powershell.exe" not in source


def test_windows_autostart_plan_keeps_scheduler_owning_the_supervisor():
    planned = [spec.to_dict() for spec in windows_runtime_specs(ROOT)]
    supervisor = next(
        task for task in planned if task["name"] == "HiveMind-Supervisor"
    )
    assert supervisor["execute"] == str(expected_gui_launchers(ROOT)["hive-mind-supervisorw"])
    assert "--project-root" in supervisor["arguments"]
    assert ".ps1" not in supervisor["arguments"].lower()
    assert supervisor["start_when_available"] is True
    assert supervisor["restart_count"] >= 3
    assert supervisor["execution_time_limit"] == "PT0S"


def test_windows_runtime_tasks_use_only_project_python():
    expected = expected_gui_launchers(ROOT)
    planned = [spec.to_dict() for spec in windows_runtime_specs(ROOT)]
    assert {task["name"] for task in planned} == {
        "HiveMind-Supervisor",
        "HiveMind-PostRebootValidation",
    }
    assert {task["execute"] for task in planned} == {
        str(expected["hive-mind-supervisorw"]),
        str(expected["hive-mind-post-rebootw"]),
    }
    for task in planned:
        assert ".ps1" not in str(task["arguments"]).lower()
        assert ".vbs" not in str(task["arguments"]).lower()


def test_supervisor_js_serializes_concurrent_starts_with_a_startup_lock():
    source = (ROOT / "npm" / "lib" / "supervisor.js").read_text(encoding="utf-8")

    assert "startupLock: path.join(dir, 'supervisor.start.lock')" in source
    assert "fs.openSync(p.startupLock, 'wx')" in source
    assert "supervisor start already in progress" in source


def test_claude_mem_runtime_uses_the_python_launcher():
    source = (ROOT / "src" / "hive_mind" / "maintenance" / "runtime_services.py").read_text(encoding="utf-8")
    assert "hive_mind.services.claude_mem_launcher" in source
    assert "claude-mem-local.ps1" not in source
    assert "pythonw.exe" not in source


def test_windows_autostart_plan_never_recreates_watchdog():
    planned = [spec.to_dict() for spec in windows_runtime_specs(ROOT)]
    assert "HiveMind-Supervisor-Watchdog" not in {
        task["name"] for task in planned
    }


def test_local_full_reuses_complete_canonical_container_sets():
    source = NATIVE_INSTALL.read_text(encoding="utf-8")

    assert 'print(f"Reusing existing {name} containers:' in source
    assert "partial existing container set" in source
    assert 'containers=["sinapse-falkordb"]' in source
    assert 'containers=["hive-mind-milvus"]' in source
    assert '"hive-mind-ragflow-mysql", "es01", "redis", "minio", "hive-mind-ragflow"' in source


def test_native_windows_install_uses_the_python_fullstack_readiness_owner():
    source = NATIVE_INSTALL.read_text(encoding="utf-8")

    assert "test_fullstack_readiness" in source
    assert "test_http_readiness" in source
    assert "fullstack-readiness.ps1" not in source


def test_ragflow_compose_uses_a_minio_host_without_an_embedded_port():
    source = (ROOT / "integrations" / "ragflow" / "docker-compose.yml").read_text(encoding="utf-8")

    assert 'MINIO_HOST: "minio"' in source
    assert 'MINIO_HOST: "minio:9000"' not in source

def test_vault_materialization_initializes_the_runtime_vault_path_before_use():
    source = NATIVE_INSTALL.read_text(encoding="utf-8")
    section = source[source.index("def _materialize_vault"):source.index("def build_parser")]

    assert 'vault = root / "cerebro"' in section
    assert section.index('vault = root / "cerebro"') < section.index("sync_vault_templates(root)")
    assert section.index('vault = root / "cerebro"') < section.index("(vault / rel).mkdir")

def test_initial_graph_bootstrap_defers_optional_hnsw_embedding_work():
    source = NATIVE_INSTALL.read_text(encoding="utf-8")
    section = source[source.index('_step("Graph/index bootstrap")'):source.index("if not args.skip_agents:")]

    assert '[project_python, "-m", "graphify", "update", str(root / "cerebro")]' in section
    assert "build-graph.ps1" not in section
