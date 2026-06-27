#!/usr/bin/env python3
"""Compatibility CLI for the import-safe sinapse_sync module.

O nome hifenizado é mantido por compatibilidade com docs/uso manual. A lógica
vive em sinapse_sync.py, que é importável diretamente (consumido pelo
sinapse-api.py sem importlib).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.services.sinapse_sync import main


if __name__ == "__main__":
    sys.exit(main())
