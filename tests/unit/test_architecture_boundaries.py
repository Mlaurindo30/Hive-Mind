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


# A legacy script name may appear in executable code when it is part of a
# *recognition* constant rather than an invocation. The instruction installer
# must know the marker register-mcp.ps1 wrote, otherwise it would append a
# second managed block beside the old one instead of replacing it.
RECOGNITION_ALLOWANCES = {
    "agents/instructions.py": {"register-mcp.ps1"},
}


class TestNativeCodeDoesNotDelegateToLegacyScripts:
    def test_no_module_executes_a_legacy_script(self):
        offenders = []
        for path in _python_sources():
            code = _code_without_docstrings(path)
            allowed = RECOGNITION_ALLOWANCES.get(path.relative_to(SRC).as_posix(), set())
            for marker in LEGACY_SCRIPT_MARKERS:
                if marker in code and marker not in allowed:
                    offenders.append(f"{path.relative_to(ROOT)}: {marker}")
        assert offenders == [], (
            "native code must implement behaviour directly, never shell out to "
            f"a legacy script: {offenders}"
        )

    def test_recognition_allowances_are_still_needed(self):
        """An allowance that stopped being used must be removed, not linger."""
        for rel, markers in RECOGNITION_ALLOWANCES.items():
            code = _code_without_docstrings(SRC / rel)
            stale = {m for m in markers if m not in code}
            assert stale == set(), f"{rel}: drop unused allowances {sorted(stale)}"

    def test_allowed_mentions_are_not_invocations(self):
        """The allowance covers naming a marker, never running the script."""
        for rel in RECOGNITION_ALLOWANCES:
            code = _code_without_docstrings(SRC / rel)
            for smell in ("subprocess", "os.system", "Popen"):
                assert smell not in code, f"{rel} invokes something: {smell}"

    def test_no_module_spawns_powershell_or_bash(self):
        offenders = []
        for path in _python_sources():
            code = _code_without_docstrings(path).lower()
            for shell in ("powershell", "pwsh.exe", "bash -c", "cmd.exe"):
                if shell in code:
                    offenders.append(f"{path.relative_to(ROOT)}: {shell}")
        assert offenders == []

    def test_only_the_supervisor_spawns_processes(self):
        """subprocess is not a free-for-all.

        Two modules may use it, for different and documented reasons:

        - `daemon/managed.py` supervises services declared in the manifest;
        - `projects/identity.py` invokes `git` to read repository facts
          (toplevel, common-dir, branch, remote). That is a tool being queried
          for data, not a service being spawned;
        - `implementation/validate.py` and `implementation/status.py` invoke
          `git` for the same reason — HEAD, branch and the commit list are the
          ground truth the living documents are checked against. Reading that
          from anything but git would defeat the check;
        - `security/secret_scan.py` invokes `git` to read the object store
          while auditing a leaked credential. It reads blobs *through* git
          precisely so the secret never becomes a command-line argument, which
          is what `git grep <secret>` would do.

        The prohibitions that matter are enforced separately and still hold
        for every module: no legacy script is executed, and no shell
        (powershell/pwsh/bash/cmd) is spawned.
        """
        allowed = {
            "daemon/managed.py",
            "projects/identity.py",
            "implementation/validate.py",
            "implementation/status.py",
            "security/secret_scan.py",
        }
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


class TestSingleProjectIdentityImplementation:
    """D003-R1: identity lives in the package; the legacy path only re-exports."""

    def test_native_module_is_the_implementation(self):
        from hive_mind.projects import identity

        assert hasattr(identity, "ProjectIdentityResolver")
        source = Path(identity.__file__).read_text(encoding="utf-8")
        assert "class ProjectIdentityResolver" in source

    def test_legacy_path_holds_no_copy(self):
        legacy = ROOT / "scripts" / "capture" / "project_identity.py"
        if not legacy.exists():
            return  # already removed — even better
        source = legacy.read_text(encoding="utf-8")
        for definition in (
            "class ProjectIdentityResolver",
            "class ProjectAliasRegistry",
            "class ProjectIdentity(",
            "def normalize_git_remote",
        ):
            assert definition not in source, (
                f"a second implementation reappeared in {legacy.name}: {definition}"
            )

    def test_legacy_re_export_yields_the_same_objects(self):
        import importlib

        native = importlib.import_module("hive_mind.projects.identity")
        try:
            shim = importlib.import_module("scripts.capture.project_identity")
        except ModuleNotFoundError:
            return  # legacy path gone
        assert shim.ProjectIdentityResolver is native.ProjectIdentityResolver
        assert shim.ProjectAliasRegistry is native.ProjectAliasRegistry


class TestRegisterIsSafeByDefault:
    def test_register_providers_defaults_to_dry_run(self):
        import inspect

        from hive_mind.agents.register import register_providers

        default = inspect.signature(register_providers).parameters["dry_run"].default
        assert default is True, "agents register must never write unless asked"


class TestDeprecatedOutboxStaysUnwired:
    """ADR-004: neither installer may re-wire the outbox delivery path.

    Both are asserted, because they diverged once: the .ps1 was fixed in
    b329e84 while the .sh kept invoking install-capture-hooks.py, leaving a
    second delivery owner alive on POSIX.
    """

    @pytest.mark.parametrize("script_name", ["register-mcp.ps1", "register-mcp.sh"])
    def test_installer_does_not_install_capture_hooks(self, script_name):
        script = ROOT / "scripts" / "setup" / script_name
        executable = [
            line
            for line in script.read_text(encoding="utf-8-sig").splitlines()
            if not line.strip().startswith("#")
        ]
        offenders = [
            line
            for line in executable
            if "install-capture-hooks" in line or "install_capture_hooks" in line
        ]
        assert offenders == [], f"{script_name} re-wires the outbox: {offenders}"

    def test_both_installers_agree(self):
        """The two installers must not diverge on delivery ownership."""
        setup = ROOT / "scripts" / "setup"
        wired = {}
        for name in ("register-mcp.ps1", "register-mcp.sh"):
            lines = [
                line
                for line in (setup / name).read_text(encoding="utf-8-sig").splitlines()
                if not line.strip().startswith("#")
            ]
            wired[name] = any("capture-hook" in line or "capture_hook" in line for line in lines)
        assert len(set(wired.values())) == 1, f"installers diverge: {wired}"


class TestTheBridgeRecoversAndNeverDecides:
    """M14 / ADR-014: the ingest decides, the bridge looks it up.

    Having two places decide identity is what produced
    `preciso-que-verifique-o-por-que-3` as a project name. The bridge reads a
    recorded decision through a declared foreign key; it does not consult git,
    the working directory, the alias registry, or the observation's own label.
    """

    BRIDGE = ROOT / "core" / "knowledge" / "claude_mem_bridge.py"
    LOOKUP = SRC / "capture" / "observation_identity.py"

    def _bridge_code(self) -> str:
        return _code_without_docstrings(self.BRIDGE)

    @pytest.mark.parametrize("forbidden", [
        "ProjectIdentityResolver",
        "resolve_project_identity",
        "attach_project_identity",
        "resolve_identity(",
    ])
    def test_the_bridge_never_resolves_identity(self, forbidden):
        assert forbidden not in self._bridge_code(), (
            f"the bridge calls {forbidden}; it must recover, not decide"
        )

    @pytest.mark.parametrize("forbidden", ["subprocess", "os.getcwd", "Path.cwd"])
    def test_the_bridge_reads_no_environment(self, forbidden):
        assert forbidden not in self._bridge_code(), (
            f"the bridge consults {forbidden} — identity is not re-derived here"
        )

    def test_the_bridge_never_slugs_a_label_into_an_id(self):
        code = self._bridge_code()
        for smell in ("_slug(", "slugify(", "project_name.lower()"):
            assert smell not in code, f"the bridge derives an id from a label: {smell}"

    def test_the_lookup_follows_the_foreign_key(self):
        """Not the id's shape: a format change must fail loudly, not silently."""
        code = _code_without_docstrings(self.LOOKUP)
        assert "FROM sdk_sessions WHERE memory_session_id" in code
        for smell in (".split(", ".removeprefix(", "re.match", "startswith(\"openrouter"):
            assert smell not in code, (
                f"the lookup parses the memory_session_id shape: {smell}"
            )

    def test_the_lookup_never_reads_the_observation_label(self):
        code = _code_without_docstrings(self.LOOKUP)
        assert "observations.project" not in code
        assert "SELECT project FROM observations" not in code
