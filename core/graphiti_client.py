"""Graphiti temporal graph client for Hive-Mind.

Wraps graphiti-core with FalkorDB backend + Ollama LLM/embedder.
Used by dream_cycle to push synthesized neurons into the temporal graph
and by sinapse-mcp to expose temporal graph search.

Config (env vars):
  FALKORDB_HOST        — default: localhost
  FALKORDB_PORT        — default: 6379
  FALKORDB_USER        — default: (empty)
  FALKORDB_PASSWORD    — default: (empty)
  FALKORDB_DB          — default: sinapse
  GRAPHITI_LLM_BASE    — default: http://localhost:11434/v1
  GRAPHITI_LLM_MODEL   — default: qwen2.5-coder:3b
  GRAPHITI_EMBED_MODEL — default: bge-m3:latest
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Any

_graphiti: Any = None


def graphiti_available() -> bool:
    """Return True when FalkorDB is reachable on the configured host/port."""
    try:
        import falkordb

        host = os.environ.get("FALKORDB_HOST", "localhost")
        port = int(os.environ.get("FALKORDB_PORT", "6379"))
        falkordb.FalkorDB(host=host, port=port)
        return True
    except Exception:
        return False


def _build_client():
    from graphiti_core import Graphiti
    from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient
    from graphiti_core.driver.falkordb_driver import FalkorDriver
    from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
    from graphiti_core.llm_client.config import LLMConfig
    from graphiti_core.llm_client.openai_client import OpenAIClient

    host = os.environ.get("FALKORDB_HOST", "localhost")
    port = int(os.environ.get("FALKORDB_PORT", "6379"))
    user = os.environ.get("FALKORDB_USER") or None
    password = os.environ.get("FALKORDB_PASSWORD") or None
    database = os.environ.get("FALKORDB_DB", "sinapse")

    llm_base = os.environ.get("GRAPHITI_LLM_BASE", "http://localhost:11434/v1")
    llm_model = os.environ.get("GRAPHITI_LLM_MODEL", "qwen2.5-coder:3b")
    embed_model = os.environ.get("GRAPHITI_EMBED_MODEL", "bge-m3:latest")

    # Set small_model to the same model — prevents graphiti from falling back to
    # the default "gpt-4.1-nano" when running against a local Ollama endpoint.
    llm_cfg = LLMConfig(
        api_key="ollama", model=llm_model, base_url=llm_base, small_model=llm_model
    )
    driver = FalkorDriver(
        host=host, port=port, username=user, password=password, database=database
    )
    llm = OpenAIClient(config=llm_cfg)
    embedder = OpenAIEmbedder(
        config=OpenAIEmbedderConfig(
            api_key="ollama", base_url=llm_base, embedding_model=embed_model
        )
    )
    # Graphiti also creates a cross_encoder internally — pass one with Ollama config
    # so it doesn't fall back to looking for OPENAI_API_KEY in the environment.
    cross_encoder = OpenAIRerankerClient(config=llm_cfg)
    return Graphiti(
        graph_driver=driver,
        llm_client=llm,
        embedder=embedder,
        cross_encoder=cross_encoder,
    )


def _client() -> Any:
    global _graphiti
    if _graphiti is None:
        _graphiti = _build_client()
    return _graphiti


def push_neuron(neuron_id: str, content: str, source: str = "dream") -> bool:
    """Push a synthesized neuron into the temporal graph as an episode.

    Returns True on success. Swallows all errors so dream_cycle never fails
    because of Graphiti being unavailable.
    """
    if not graphiti_available():
        return False
    try:
        from graphiti_core.nodes import EpisodeType

        asyncio.run(
            _client().add_episode(
                name=f"neuron:{neuron_id}",
                episode_body=content[:4000],
                source_description=f"Hive-Mind dream — neuron {neuron_id} ({source})",
                reference_time=datetime.now(timezone.utc),
                source=EpisodeType.text,
                group_id="hive-mind",
            )
        )
        return True
    except Exception as e:
        print(f"  [graphiti] push_neuron failed for {neuron_id}: {e}")
        return False


def search_graph(query: str, num_results: int = 10) -> list[dict]:
    """Search the temporal graph for relevant facts/edges.

    Returns list of {fact, valid_at, invalid_at, uuid} dicts.
    Returns [] when FalkorDB is unreachable or on any error.
    """
    if not graphiti_available():
        return []
    try:
        edges = asyncio.run(
            _client().search(
                query=query,
                group_ids=["hive-mind"],
                num_results=num_results,
            )
        )
        return [
            {
                "fact": getattr(edge, "fact", str(edge)),
                "valid_at": str(getattr(edge, "valid_at", "")),
                "invalid_at": str(getattr(edge, "invalid_at", "")),
                "uuid": str(getattr(edge, "uuid", "")),
            }
            for edge in edges
        ]
    except Exception as e:
        print(f"  [graphiti] search failed: {e}")
        return []
