"""
Constantes de configuração padrão e helper de log para Sinapse Memory.

Estas são os valores DEFAULT. O módulo plugins/hermes/sinapse-memory.py
re-exporta como variáveis mutáveis — os testes fazem monkeypatch nelas,
não aqui.
"""

import json
import os
import sys
from datetime import datetime
from typing import Any

# ---------------------------------------------------------------------------
# Defaults de conexão / timeouts
# ---------------------------------------------------------------------------

DEFAULT_CLAUDE_MEM_URL = "http://127.0.0.1:37700"
DEFAULT_CLAUDE_MEM_TIMEOUT = 3
DEFAULT_NMEM_BIN = os.path.expanduser("~/.local/bin/nmem")
DEFAULT_NMEM_TIMEOUT = 5
DEFAULT_VEC_WORKER_URL = "http://127.0.0.1:37701"

# ---------------------------------------------------------------------------
# Defaults de limites / janelas
# ---------------------------------------------------------------------------

DEFAULT_GLOBAL_QUERY_TIMEOUT = 8
DEFAULT_MAX_CONTEXT_CHARS = 3000
DEFAULT_MAX_NODES = 5
DEFAULT_MAX_OBSERVATIONS = 5
DEFAULT_OBSERVATION_CHARS = 300
DEFAULT_SEMANTIC_CONTEXT_CHARS = 500
DEFAULT_GRAPH_CACHE_TTL = 60

# ---------------------------------------------------------------------------
# Defaults de comportamento
# ---------------------------------------------------------------------------

DEFAULT_DECISION_TOOLS: frozenset = frozenset(
    {"memory_add", "observation_add", "mcp_claude_mem_memory_add"}
)

DEFAULT_LEARNING_SIGNALS = [
    # Português
    "aprendizado", "aprendizagem", "lição", "lição aprendida",
    "descoberta", "padrão identificado",
    # Inglês
    "learning", "insight", "pattern", "lesson",
    "lesson learned", "takeaway", "finding", "aha",
    "note to self", "tl;dr",
    # Espanhol
    "aprendizaje", "lección", "descubrimiento",
]


# ---------------------------------------------------------------------------
# Logging estruturado (puro — sem acesso a globals do módulo pai)
# ---------------------------------------------------------------------------


def log(level: str, event: str, log_json: bool = False, **kwargs: Any) -> None:
    """Log estruturado. Sempre escreve em stderr."""
    if log_json:
        entry = {"ts": datetime.now().isoformat(), "level": level, "event": event, **kwargs}
        print(json.dumps(entry), file=sys.stderr)
    else:
        extra = " ".join(f"{k}={v}" for k, v in kwargs.items())
        print(f"[sinapse] {level.upper()}: {event} {extra}".strip(), file=sys.stderr)


# ---------------------------------------------------------------------------
# Loader de sinapse.yaml
# ---------------------------------------------------------------------------


def load_yaml_config(sinapse_home: str) -> dict:
    """Carrega sinapse.yaml se disponível."""
    config_path = os.path.join(sinapse_home, "sinapse.yaml")
    if os.path.isfile(config_path):
        try:
            import yaml  # optional dependency
            with open(config_path) as f:
                return yaml.safe_load(f)
        except Exception:
            pass
    return {}
