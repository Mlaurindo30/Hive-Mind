"""Import-safe adapter for the legacy ``sinapse-memory.py`` plugin file.

The Hermes plugin filename is kept for compatibility with existing installers.
Python callers should import this module instead of loading the hyphenated file
with ``importlib`` in every entrypoint.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


_LEGACY_MODULE_NAME = "sinapse_memory_legacy"
_LEGACY_PATH = Path(__file__).with_name("sinapse-memory.py")

if _LEGACY_MODULE_NAME in sys.modules:
    _module = sys.modules[_LEGACY_MODULE_NAME]
else:
    _spec = importlib.util.spec_from_file_location(_LEGACY_MODULE_NAME, _LEGACY_PATH)
    if _spec is None or _spec.loader is None:
        raise ImportError(f"Cannot load legacy sinapse-memory plugin at {_LEGACY_PATH}")
    _module = importlib.util.module_from_spec(_spec)
    sys.modules[_LEGACY_MODULE_NAME] = _module
    _spec.loader.exec_module(_module)

sys.modules.setdefault("sinapse_memory", _module)

for _name in dir(_module):
    if _name.startswith("__") and _name not in {"__all__", "__doc__"}:
        continue
    globals()[_name] = getattr(_module, _name)

__all__ = getattr(_module, "__all__", [name for name in globals() if not name.startswith("_")])
