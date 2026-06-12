import os
import sys
from pathlib import Path
import importlib.util
import pytest

_plugin_path = Path(__file__).parent.parent.parent / "plugins" / "hermes" / "sinapse-memory.py"
if "sinapse_memory" not in sys.modules:
    spec = importlib.util.spec_from_file_location("sinapse_memory", _plugin_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sinapse_memory"] = mod
    spec.loader.exec_module(mod)


@pytest.fixture(scope="module")
def ensure_backends():
    """Garante que backends reais estão operacionais.

    Delegates entirely to ``sinapse_memory.health_check()`` — the same check
    that ``scripts/sinapse-write.py health`` runs — so the fixture stays in
    sync with the actual plugin logic.  If any backend reports unhealthy the
    tests are skipped with a diagnostic message rather than giving a false
    pass or a cryptic failure.
    """
    sinapse_memory = sys.modules["sinapse_memory"]
    try:
        status = sinapse_memory.health_check()
    except Exception as exc:
        pytest.skip(f"health_check() raised an unexpected error: {exc}")

    if not status.get("healthy"):
        unhealthy = [
            name
            for name, ok in status.get("backends", {}).items()
            if not ok
        ]
        pytest.skip(
            "sinapse-memory backends not available: "
            + (", ".join(unhealthy) if unhealthy else "unknown")
        )

    return True
