import os
import sys
import json
import tempfile
import shutil
from pathlib import Path
import importlib.util
import pytest

# Load the hyphenated plugin file into sys.modules before any test collects
_plugin_path = Path(__file__).parent.parent / "plugins" / "hermes" / "sinapse-memory.py"
if "sinapse_memory" not in sys.modules:
    spec = importlib.util.spec_from_file_location("sinapse_memory", _plugin_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sinapse_memory"] = mod
    spec.loader.exec_module(mod)

import sinapse_memory as _sm

# Capture original global state at import time (once)
_ORIGINAL_BACKENDS = tuple(_sm._READ_BACKENDS)
_ORIGINAL_BACKEND_STATE = {}
_ORIGINAL_GRAPH_CACHE = {}
_ORIGINAL_CACHE_TIME = 0.0
_ORIGINAL_GRAPH_JSON = _sm.GRAPH_JSON
_ORIGINAL_MAX_NODES = _sm.MAX_NODES
_ORIGINAL_MAX_OBSERVATIONS = _sm.MAX_OBSERVATIONS
_ORIGINAL_MAX_CONTEXT = _sm.MAX_CONTEXT_CHARS
_ORIGINAL_NMEM_BIN = _sm.NMEM_BIN


def _restore_original_state():
    """Restore module globals to original values."""
    _sm._READ_BACKENDS.clear()
    _sm._READ_BACKENDS.extend(_ORIGINAL_BACKENDS)
    _sm._backend_state.clear()
    _sm._graph_cache.clear()
    _sm._graph_cache_time = 0.0
    _sm.GRAPH_JSON = _ORIGINAL_GRAPH_JSON
    _sm.MAX_NODES = _ORIGINAL_MAX_NODES
    _sm.MAX_OBSERVATIONS = _ORIGINAL_MAX_OBSERVATIONS
    _sm.MAX_CONTEXT_CHARS = _ORIGINAL_MAX_CONTEXT
    _sm.NMEM_BIN = _ORIGINAL_NMEM_BIN


@pytest.fixture(autouse=True)
def _reset_global_state():
    """Reset global module state between tests to prevent cross-test leakage."""
    _restore_original_state()
    yield
    _restore_original_state()


@pytest.fixture
def sample_graph():
    """Grafo mínimo para testes unitários."""
    return {
        "nodes": [
            {"label": "thoth", "file_type": "document", "source_file": "thoth.md", "id": "thoth", "community": 1, "norm_label": "thoth"},
            {"label": "vps", "file_type": "document", "source_file": "vps.md", "id": "vps", "community": 2, "norm_label": "vps"},
            {"label": "pricing", "file_type": "document", "source_file": "pricing.md", "id": "pricing", "community": 3, "norm_label": "pricing"},
            {"label": "deploy", "file_type": "code", "source_file": "deploy.sh", "id": "deploy", "community": 2, "norm_label": "deploy"},
            {"label": "database", "file_type": "code", "source_file": "db.py", "id": "database", "community": 4, "norm_label": "database"},
        ],
        "links": [
            {"source": "thoth", "target": "vps", "relation": "related_to", "confidence": "EXTRACTED", "source_file": "thoth.md", "source_location": "L5", "weight": 1.0, "confidence_score": 1.0},
            {"source": "vps", "target": "deploy", "relation": "managed_by", "confidence": "EXTRACTED", "source_file": "vps.md", "source_location": "L10", "weight": 1.0, "confidence_score": 1.0},
            {"source": "database", "target": "deploy", "relation": "depends_on", "confidence": "EXTRACTED", "source_file": "db.py", "source_location": "L3", "weight": 1.0, "confidence_score": 1.0},
        ],
    }


@pytest.fixture
def temp_vault():
    """Vault temporário isolado para testes de escrita."""
    tmp = tempfile.mkdtemp()
    os.makedirs(f"{tmp}/work/active", exist_ok=True)
    os.makedirs(f"{tmp}/brain", exist_ok=True)
    os.makedirs(f"{tmp}/graphify-out", exist_ok=True)
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def sample_graph_file(sample_graph, tmp_path):
    """Escreve sample_graph em arquivo temporário e retorna path."""
    path = tmp_path / "graph.json"
    path.write_text(json.dumps(sample_graph))
    return str(path)
