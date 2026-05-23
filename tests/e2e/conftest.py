import os
import sys
from pathlib import Path
import importlib.util

_plugin_path = Path(__file__).parent.parent.parent / "plugins" / "hermes" / "sinapse-memory.py"
if "sinapse_memory" not in sys.modules:
    spec = importlib.util.spec_from_file_location("sinapse_memory", _plugin_path)
    sinapse_memory = importlib.util.module_from_spec(spec)
    sys.modules["sinapse_memory"] = sinapse_memory
    spec.loader.exec_module(sinapse_memory)
