#!/usr/bin/env python3
"""Compatibility entrypoint for the import-safe sinapse_mcp module.

O nome hifenizado é mantido por compatibilidade com a config MCP dos agentes
(register-mcp.sh aponta para este caminho). A lógica vive em sinapse_mcp.py,
que é importável diretamente — sem importlib nos consumidores.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.services.sinapse_mcp import main


if __name__ == "__main__":
    main()
