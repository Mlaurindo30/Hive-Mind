#!/usr/bin/env python3
import sys
import json
from pathlib import Path

# Adiciona o diretório raiz ao path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

from core.auth import discover_models_realtime

def main():
    models = discover_models_realtime()
    print(json.dumps(models, indent=2))

if __name__ == "__main__":
    main()
