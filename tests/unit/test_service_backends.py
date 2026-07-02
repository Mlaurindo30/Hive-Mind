"""Backends multiplataforma de serviços (F2/F3 do plano npm).

- service_specs() é a fonte para launchd (macOS) e manifesto (supervisor Node).
- O gerador systemd (unit_definitions) segue sendo a referência no Linux;
  estes testes travam a consistência entre as duas representações para o
  conjunto de serviços daemon coberto pelas specs.
"""
import plistlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "setup"))

import install_services as isvc  # noqa: E402


def test_specs_cover_core_daemons():
    names = {s["name"] for s in isvc.service_specs()}
    assert {
        "sinapse-claude-mem",
        "sinapse-sqlite-vec",
        "sinapse-graphify-watch",
        "sinapse-api",
        "sinapse-mcp-http",
        "hive-otel-collector",
        "sinapse-capture-realtime",
    } <= names


def test_specs_consistent_with_systemd_units():
    """Cada spec deve bater com a unit systemd correspondente (exec + env)."""
    units = isvc.unit_definitions()
    for spec in isvc.service_specs():
        unit = units[f"{spec['name']}.service"]
        exec_line = next(l for l in unit.splitlines() if l.startswith("ExecStart="))
        assert exec_line == "ExecStart=" + " ".join(spec["command"]), spec["name"]
        for key, value in spec["env"].items():
            assert f"Environment={key}={value}" in unit, f"{spec['name']}: {key}"
        if spec.get("env_file"):
            assert f"EnvironmentFile={spec['env_file']}" in unit, spec["name"]
        expected_restart = "always" if spec["restart"] == "always" else "on-failure"
        assert f"Restart={expected_restart}" in unit, spec["name"]
        assert f"RestartSec={spec['restart_sec']}" in unit, spec["name"]


def test_launchd_plists_are_valid_and_faithful():
    plists = isvc.launchd_definitions()
    specs = {s["name"]: s for s in isvc.service_specs()}
    assert len(plists) == len(specs)
    for filename, blob in plists.items():
        payload = plistlib.loads(blob)
        name = payload["Label"].removeprefix(isvc.LAUNCHD_LABEL_PREFIX)
        spec = specs[name]
        assert filename == f"{payload['Label']}.plist"
        assert payload["WorkingDirectory"] == str(isvc.ROOT)
        assert payload["EnvironmentVariables"] == spec["env"]
        assert payload["ThrottleInterval"] == spec["restart_sec"]
        assert payload["RunAtLoad"] is True
        assert payload["Umask"] == 0o077
        if spec["restart"] == "always":
            assert payload["KeepAlive"] is True
        else:
            assert payload["KeepAlive"] == {"SuccessfulExit": False}
        if spec.get("env_file"):
            # .env é carregado em runtime via sh — nunca congelado no plist.
            assert payload["ProgramArguments"][0] == "/bin/sh"
            assert spec["env_file"] in payload["ProgramArguments"][2]
            assert " ".join(spec["command"]) not in str(payload["EnvironmentVariables"])
        else:
            assert payload["ProgramArguments"] == spec["command"]


def test_manifest_shape_for_node_supervisor():
    m = isvc.manifest()
    assert m["manifest_version"] == 1
    assert m["root"] == str(isvc.ROOT)
    assert isinstance(m["claude_mem_plugin_available"], bool)
    for svc in m["services"]:
        assert svc["name"] and svc["description"]
        assert isinstance(svc["command"], list) and svc["command"]
        assert svc["restart"] in {"on-failure", "always"}
        assert isinstance(svc["restart_sec"], int)
