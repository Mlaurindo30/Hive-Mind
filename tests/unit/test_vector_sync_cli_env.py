from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_vector_sync_cli_loads_project_env_before_vector_backend_import():
    source = (ROOT / "scripts" / "maintenance" / "vector-sync.py").read_text(encoding="utf-8")

    assert "from core.auth import load_env" in source
    assert source.index("load_env()") < source.index("from core.vector_backend import MilvusBackend")
