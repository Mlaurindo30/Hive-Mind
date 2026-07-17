from __future__ import annotations

import importlib
import os
import subprocess
import tempfile

import pytest


pytestmark = pytest.mark.real


def _has_ollama_model(model: str) -> bool:
    try:
        result = subprocess.run(
            ["ollama", "list"], capture_output=True, text=True, timeout=10, check=False
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return any(line.split() and line.split()[0] == model for line in result.stdout.splitlines())


@pytest.mark.timeout(180)
def test_lightrag_answers_real_two_hop_query_in_isolated_storage():
    """Indexa relações reais no Ollama e responde o caminho multi-hop."""
    if not _has_ollama_model("qwen2.5:3b"):
        pytest.skip("qwen2.5:3b não está instalado no Ollama local")

    from core.auth import load_env

    load_env()
    original_home = os.environ.get("SINAPSE_HOME")
    original_model = os.environ.get("HIVE_LIGHTRAG_MODEL")
    try:
        with tempfile.TemporaryDirectory(prefix="hive-real-lightrag-") as storage_root:
            os.environ["SINAPSE_HOME"] = storage_root
            os.environ["HIVE_LIGHTRAG_MODEL"] = "qwen2.5:3b"
            import core.lightrag_index as lightrag_index

            lightrag_index = importlib.reload(lightrag_index)
            assert lightrag_index.index_memory_sync(
                "Asteria is an organization. Boreal is an organization. "
                "Cirios is an organization. Asteria administers Boreal. "
                "Boreal coordinates Cirios."
            )
            answer = lightrag_index.query_rag_sync(
                "Using the indexed graph, state the exact two-hop path from "
                "Asteria to Cirios. Do not require a direct edge.",
                mode="hybrid",
            ).lower()
            assert "[no-context]" not in answer
            # The model may paraphrase relationship verbs and path notation,
            # but it must identify the requested two-hop route and its nodes.
            for term in ("asteria", "boreal", "cirios"):
                assert term in answer
            assert "two-hop" in answer
    finally:
        if original_home is None:
            os.environ.pop("SINAPSE_HOME", None)
        else:
            os.environ["SINAPSE_HOME"] = original_home
        if original_model is None:
            os.environ.pop("HIVE_LIGHTRAG_MODEL", None)
        else:
            os.environ["HIVE_LIGHTRAG_MODEL"] = original_model
        import core.lightrag_index as lightrag_index

        importlib.reload(lightrag_index)
