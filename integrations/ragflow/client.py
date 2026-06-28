"""RAGFlow wrapper for Hive-Mind K1/K6.

RAGFlow is treated as a headless ingestion adapter/cache. The canonical memory
remains `cerebro/` plus UMC; this wrapper only validates SDK connectivity and
provides a single place for env parsing.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
import urllib.request
from typing import Any


@dataclass(frozen=True)
class RAGFlowSettings:
    base_url: str
    api_key: str
    version: str = "v1"
    timeout: float = 2.0


def settings_from_env() -> RAGFlowSettings:
    return RAGFlowSettings(
        base_url=os.environ.get("RAGFLOW_BASE", os.environ.get("RAGFLOW_API_URL", "http://localhost:9380")).rstrip("/"),
        api_key=os.environ.get("RAGFLOW_API_KEY", ""),
        version=os.environ.get("RAGFLOW_API_VERSION", "v1"),
        timeout=float(os.environ.get("RAGFLOW_TIMEOUT", "2.0")),
    )


def create_client(settings: RAGFlowSettings | None = None):
    from ragflow_sdk import RAGFlow

    s = settings or settings_from_env()
    if not s.api_key:
        raise ValueError("RAGFLOW_API_KEY nao configurado")
    return RAGFlow(api_key=s.api_key, base_url=s.base_url, version=s.version)


def _http_health(settings: RAGFlowSettings) -> tuple[bool, str]:
    for path in ("/api/v1/health", "/"):
        url = f"{settings.base_url}{path}"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=settings.timeout) as response:
                if 200 <= response.status < 500:
                    return True, f"HTTP {response.status} em {url}"
        except Exception as exc:
            last = f"{type(exc).__name__}: {exc}"
    return False, last


def assert_health(*, strict: bool = True, settings: RAGFlowSettings | None = None) -> dict[str, Any]:
    """Return real RAGFlow wrapper health; raise only when `strict=True`."""
    s = settings or settings_from_env()
    try:
        client = create_client(s)
        http_ok, reason = _http_health(s)
        result = {
            "ok": http_ok,
            "service": "ragflow",
            "endpoint": s.base_url,
            "version": s.version,
            "sdk_client": client.__class__.__name__,
            "reason": reason,
        }
        if strict and not http_ok:
            raise RuntimeError(reason)
        return result
    except Exception as exc:
        result = {
            "ok": False,
            "service": "ragflow",
            "endpoint": s.base_url,
            "version": s.version,
            "error": type(exc).__name__,
            "reason": str(exc),
        }
        if strict:
            raise RuntimeError(f"RAGFlow indisponivel em {s.base_url}: {exc}") from exc
        return result


__all__ = ["RAGFlowSettings", "assert_health", "create_client", "settings_from_env"]
