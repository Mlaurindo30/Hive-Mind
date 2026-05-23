import importlib.util
from pathlib import Path
import sys

_plugin_path = Path(__file__).parent.parent / "plugins" / "hermes" / "sinapse-memory.py"
if "sinapse_memory" not in sys.modules:
    spec = importlib.util.spec_from_file_location("sinapse_memory", _plugin_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sinapse_memory"] = mod
    spec.loader.exec_module(mod)
