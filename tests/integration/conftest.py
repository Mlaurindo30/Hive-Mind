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
    """Garante que backends reais estão operacionais."""
    import urllib.request
    import json

    try:
        req = urllib.request.Request("http://127.0.0.1:37700/health")
        with urllib.request.urlopen(req, timeout=3) as resp:
            assert json.loads(resp.read()).get("status") == "ok"
    except Exception:
        pytest.skip("claude-mem worker not available")

    if not os.path.isfile(os.path.expanduser("~/.local/bin/nmem")):
        pytest.skip("nmem not installed")

    return True
