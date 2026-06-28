"""Milvus wrapper for Hive-Mind K1/K2.

This module is intentionally thin: application code should depend on
`core.vector_backend`, while setup/tests may use this wrapper to validate the
real Milvus SDK and local service health.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any


@dataclass(frozen=True)
class MilvusSettings:
    uri: str
    user: str = ""
    password: str = ""
    token: str = ""
    db_name: str = ""
    timeout: float = 2.0


def settings_from_env() -> MilvusSettings:
    uri = os.environ.get("MILVUS_URI")
    if not uri:
        host = os.environ.get("MILVUS_HOST", "localhost")
        port = os.environ.get("MILVUS_PORT", "19530")
        uri = f"http://{host}:{port}"
    return MilvusSettings(
        uri=uri,
        user=os.environ.get("MILVUS_USER", ""),
        password=os.environ.get("MILVUS_PASSWORD", ""),
        token=os.environ.get("MILVUS_TOKEN", ""),
        db_name=os.environ.get("MILVUS_DB_NAME", ""),
        timeout=float(os.environ.get("MILVUS_TIMEOUT", "2.0")),
    )


def create_client(settings: MilvusSettings | None = None):
    from pymilvus import MilvusClient

    s = settings or settings_from_env()
    return MilvusClient(
        uri=s.uri,
        user=s.user,
        password=s.password,
        token=s.token,
        db_name=s.db_name,
        timeout=s.timeout,
    )


def assert_health(*, strict: bool = True, settings: MilvusSettings | None = None) -> dict[str, Any]:
    """Return real Milvus health; raise only when `strict=True`.

    The health probe uses the official SDK and performs a metadata call
    (`list_collections`). Offline Milvus is an explicit unhealthy result, not a
    fake pass.
    """
    s = settings or settings_from_env()
    try:
        client = create_client(s)
        collections = client.list_collections()
        return {
            "ok": True,
            "service": "milvus",
            "endpoint": s.uri,
            "collections": len(collections),
        }
    except Exception as exc:
        result = {
            "ok": False,
            "service": "milvus",
            "endpoint": s.uri,
            "error": type(exc).__name__,
            "reason": str(exc),
        }
        if strict:
            raise RuntimeError(f"Milvus indisponivel em {s.uri}: {exc}") from exc
        return result


__all__ = ["MilvusSettings", "assert_health", "create_client", "settings_from_env"]
