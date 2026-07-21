"""D009-R2 — architectural boundaries of the native control plane.

Locks the ownership rules the project committed to:

  - product logic lives in the Python package (`src/hive_mind/**`);
  - `.ps1` / `.sh` / `.bat` / `.cmd` are thin wrappers, never product logic;
  - native code never delegates behaviour back to a legacy script;
  - exactly one agents registry namespace (ADR-013);
  - the deprecated outbox path is not re-wired (ADR-004).

These are behaviour/import assertions, not string spot-checks: they read the
real modules and the real scripts.
"""
from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "hive_mind"

LEGACY_SCRIPT_MARKERS = (
    "register-mcp.ps1",
    "register-mcp.sh",
    "install_services.py",
    "supervisor.js",
    "install-capture-hooks",
)


def _python_sources() -> list[Path]:
    return [p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts]


def _code_without_docstrings(path: Path) -> str:
    """Return the module's source with docstrings and comments removed.

    A legacy script may be *named* in a docstring as a historical reference
    (that is how the ported behaviour is documented); what must never happen is
    a legacy script being *executed*.
    """
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc and node.body and isinstance(node.body[0], ast.Expr):
                first = node.body[0]
                for line in range(first.lineno, (first.end_lineno or first.lineno) + 1):
                    docstrings.add(line)
    kept = []
    for number, line in enumerate(source.splitlines(), start=1):
        if number in docstrings:
            continue
        kept.append(line.split("#", 1)[0])
    return "\n".join(kept)


class TestNativeCodeDoesNotDelegateToLegacyScripts:
    def test_no_module_executes_a_legacy_script(self):
        offenders = []
        for path in _python_sources():
            code = _code_without_docstrings(path)
            for marker in LEGACY_SCRIPT_MARKERS:
                if marker in code:
                    offenders.append(f"{path.relative_to(ROOT)}: {marker}")
        assert offenders == [], (
            "native code must implement behaviour directly, never shell out to "
            f"a legacy script: {offenders}"
        )

    def test_no_module_spawns_powershell_or_bash(self):
        offenders = []
        for path in _python_sources():
            code = _code_without_docstrings(path).lower()
            for shell in ("powershell", "pwsh.exe", "bash -c", "cmd.exe"):
                if shell in code:
                    offenders.append(f"{path.relative_to(ROOT)}: {shell}")
        assert offenders == []

    def test_only_the_supervisor_spawns_processes(self):
        """subprocess is the managed supervisor's tool, not everyone's."""
        allowed = {"daemon/managed.py"}
        offenders = []
        for path in _python_sources():
            rel = path.relative_to(SRC).as_posix()
            if rel in allowed:
                continue
            if "subprocess" in _code_without_docstrings(path):
                offenders.append(rel)
        assert offenders == [], (
            f"only {sorted(allowed)} may spawn processes; found: {offenders}"
        )


class TestSingleAgentsRegistry:
    def test_agents_namespace_exists(self):
        importlib.import_module("hive_mind.agents.registry")

    def test_no_competing_integrations_namespace(self):
        """ADR-013: hive_mind.integrations must not exist as a second registry."""
        assert not (SRC / "integrations").exists(), (
            "hive_mind.integrations would be a competing agents registry (ADR-013)"
        )
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module("hive_mind.integrations")

    def test_provider_ids_are_unique(self):
        from hive_mind.agents.registry import PROVIDERS

        ids = [p.id for p in PROVIDERS]
        assert len(ids) == len(set(ids)), "duplicate provider id in the registry"

    def test_every_config_target_has_a_known_base(self):
        from hive_mind.agents.registry import PROVIDERS

        for spec in PROVIDERS:
            for target in spec.configs:
                assert target.base in {"home", "appdata", "project"}, (
                    f"{spec.id}: unknown config base {target.base!r}"
                )


class TestRegisterIsSafeByDefault:
    def test_register_providers_defaults_to_dry_run(self):
        import inspect

        from hive_mind.agents.register import register_providers

        default = inspect.signature(register_providers).parameters["dry_run"].default
        assert default is True, "agents register must never write unless asked"


class TestDeprecatedOutboxStaysUnwired:
    def test_register_mcp_ps1_does_not_install_capture_hooks(self):
        """ADR-004: the outbox path must not be re-wired by the installer."""
        script = ROOT / "scripts" / "setup" / "register-mcp.ps1"
        executable = [
            line
            for line in script.read_text(encoding="utf-8-sig").splitlines()
            if not line.strip().startswith("#")
        ]
        offenders = [line for line in executable if "install-capture-hooks" in line]
        assert offenders == [], f"register-mcp.ps1 re-wires the outbox: {offenders}"
