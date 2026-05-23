# Pre-load sinapse_memory before test collection
from pathlib import Path
import importlib.util
import sys

_root = Path(__file__).parent.parent
_plugin_path = _root / "plugins" / "hermes" / "sinapse-memory.py"
if "sinapse_memory" not in sys.modules:
    spec = importlib.util.spec_from_file_location("sinapse_memory", _plugin_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sinapse_memory"] = mod
    spec.loader.exec_module(mod)
