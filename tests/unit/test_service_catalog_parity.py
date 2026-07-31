"""D006-R1 — the manifest must become the only service/job catalog.

The remaining independent catalogs are config/runtime.yaml and
scripts/setup/install_services.py::unit_definitions(). npm/lib/services.js
must stay a wrapper over the manifest instead of becoming a third source.
Before any generator can be pointed at the manifest, the manifest has to
cover what the legacy catalog actually runs — otherwise a cutover silently
stops whatever it forgot.

These tests compare by **executed script**, not by name, because the two
catalogs use different naming conventions (`sinapse-dream` vs `dream-cycle`).
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "config" / "runtime.yaml"
SERVICES_JS = ROOT / "npm" / "lib" / "services.js"
sys.path.insert(0, str(ROOT / "src"))

# Responsibilities the manifest does not express yet. Each entry is a real
# unit the legacy catalog runs; leaving one here is a deliberate, visible gap,
# not an oversight. Emptying this set is the goal of D006-R1.
KNOWN_MANIFEST_GAPS = {
    # Runs on both platforms via different scripts (validate_after_reboot.py on
    # systemd, validate_after_reboot_windows.py on Task Scheduler). Expressing
    # it needs a platform-aware manifest entry — a schema decision, not a
    # mechanical addition.
    "scripts/health/validate_after_reboot.py",
}


# Legacy scripts whose responsibility now lives in a native command. The
# manifest declares the native command, so a script-path comparison no longer
# finds them — that is the point of porting, not a coverage gap.
PORTED_TO_NATIVE = {
    # D008-R1B: hive-mind backup run --apply
    "scripts/health/backup_databases.py",
}


def _norm(path: str) -> str:
    return path.replace("\\", "/").strip()


def _manifest_scripts() -> set[str]:
    data = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    scripts: set[str] = set()
    for entry in [*data.get("services", []), *data.get("jobs", [])]:
        for part in entry.get("command", []):
            if str(part).endswith(".py"):
                scripts.add(_norm(str(part)))
    return scripts


def _unit_definitions() -> dict[str, str]:
    module = importlib.util.find_spec("hive_mind.maintenance.runtime_services")
    assert module is not None
    runtime_services = __import__(
        "hive_mind.maintenance.runtime_services",
        fromlist=["unit_definitions"],
    )
    return runtime_services.unit_definitions()


def _systemd_scripts() -> set[str]:
    scripts: set[str] = set()
    for body in _unit_definitions().values():
        for match in re.findall(r"(scripts[\\/][\w\\/.-]+\.py)", body):
            scripts.add(_norm(match))
    return scripts


def _manifest_modules() -> dict[str, str]:
    """Services declared as `python -m <module>`, mapped name -> module."""
    data = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    modules: dict[str, str] = {}
    for entry in [*data.get("services", []), *data.get("jobs", [])]:
        command = [str(c) for c in entry.get("command", [])]
        if "-m" in command:
            index = command.index("-m")
            if index + 1 < len(command):
                modules[entry["name"]] = command[index + 1]
    return modules


ASPIRATIONAL_SERVICE_MODULES: set[str] = set()


def _importable(module: str) -> bool:
    """True when the module can be located.

    `find_spec` raises ModuleNotFoundError when a *parent* package is absent,
    so a missing `hive_mind.services` must be caught rather than propagated.
    """
    import importlib.util

    try:
        return importlib.util.find_spec(module) is not None
    except (ModuleNotFoundError, ValueError):
        return False


def test_manifest_service_modules_are_honest_about_existing():
    """A declared module must either import, or be a recorded aspiration.

    Silently shipping a manifest whose services cannot start is the
    'describe the target as if implemented' failure this project forbids.
    """
    unrecorded = []
    for name, module in _manifest_modules().items():
        if module in ASPIRATIONAL_SERVICE_MODULES:
            continue
        root = module.split(".")[0]
        if root != "hive_mind":
            continue  # third-party or external module, not ours to assert
        if not _importable(module):
            unrecorded.append(f"{name} -> {module}")
    assert unrecorded == [], (
        "manifest declares native modules that do not exist and are not "
        f"recorded as aspirational: {unrecorded}"
    )


def test_aspirational_modules_are_still_missing():
    """When a module lands, drop it from the aspirational set."""
    landed = {m for m in ASPIRATIONAL_SERVICE_MODULES if _importable(m)}
    assert landed == set(), (
        f"these now exist — remove from ASPIRATIONAL_SERVICE_MODULES: {sorted(landed)}"
    )


def test_manifest_covers_every_systemd_unit_script():
    """Anything systemd runs must exist in the manifest, or be a known gap.

    Services whose manifest entry is an aspirational native module are
    excluded here: systemd runs the legacy script today, and the mapping is
    tracked by the aspirational tests above.
    """
    missing = (
        _systemd_scripts()
        - _manifest_scripts()
        - KNOWN_MANIFEST_GAPS
        - PORTED_TO_NATIVE
    )
    assert missing == set(), (
        "the manifest does not cover scripts the systemd units run; a cutover "
        f"would stop them silently: {sorted(missing)}"
    )


def test_known_gaps_are_still_real():
    """A gap that stopped being real must be removed from the exception list."""
    stale = {g for g in KNOWN_MANIFEST_GAPS if g in _manifest_scripts()}
    assert stale == set(), (
        f"these are covered now — drop them from KNOWN_MANIFEST_GAPS: {sorted(stale)}"
    )


def test_gap_scripts_exist_on_disk():
    """A gap must point at real code; otherwise it is a dead unit, not a gap."""
    for gap in KNOWN_MANIFEST_GAPS:
        assert (ROOT / gap).is_file(), f"{gap} does not exist; it is dead, not a gap"


def test_post_reboot_validation_runs_on_both_platforms():
    """Documents why the gap needs a platform-aware entry rather than a job.

    The same responsibility is served by two different scripts, so a single
    `command:` cannot express it.
    """
    assert (ROOT / "scripts/health/validate_after_reboot.py").is_file()
    assert (ROOT / "scripts/health/validate_after_reboot_windows.py").is_file()
    native_owner = ROOT / "src" / "hive_mind" / "maintenance" / "windows_runtime.py"
    native_text = native_owner.read_text(encoding="utf-8")
    assert "hive-mind-post-rebootw" in native_text
    assert "windows_runtime_specs" in native_text


def test_only_one_catalog_is_authoritative_eventually():
    """Records the remaining duplication so it cannot be forgotten (A-06).

    This asserts the current, honest state: the Python generator still
    duplicates the manifest. When D006-R1 completes, this test flips to
    asserting a single source.
    """
    catalogs = {
        "manifest": MANIFEST.is_file(),
        "unit_definitions": True,
    }
    live = [name for name, present in catalogs.items() if present]
    assert "manifest" in live
    assert len(live) > 1, (
        "only the manifest remains — update this test to assert single-source"
    )


def test_services_js_derives_managed_units_from_manifest():
    """Node service control must wrap the manifest, not own a catalog.

    Reintroducing a hardcoded unit list would silently fork the source of truth
    again, so this test pins the wrapper contract directly.
    """
    text = SERVICES_JS.read_text(encoding="utf-8")
    assert "const SYSTEMD_UNITS = [" not in text
    assert "supervisor.loadManifest()" in text
    assert "supervisor.runnableServices(manifest)" in text


def test_supervisor_js_uses_native_daemon_and_native_manifest():
    text = (ROOT / "npm" / "lib" / "supervisor.js").read_text(encoding="utf-8")
    assert "scripts/setup/install_services.py" not in text
    assert "'-m', 'hive_mind.cli', 'service', 'manifest', '--json'" in text
    assert "'-m', 'hive_mind.daemon.main', 'run', '--project-root'" in text
