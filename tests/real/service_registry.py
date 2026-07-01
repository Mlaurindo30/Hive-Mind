"""Service registry for real knowledge tests.

`requires_service` markers use this module to decide whether a real backend is
available. Offline services are skipped with an explicit reason; unknown service
names are test bugs and should fail collection/setup.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import socket
from urllib.parse import urlparse
import urllib.request


@dataclass(frozen=True)
class ServiceStatus:
    name: str
    ok: bool
    reason: str
    unknown: bool = False


def marker_services(args: tuple[object, ...], kwargs: dict[str, object]) -> tuple[str, ...]:
    """Normalize `@pytest.mark.requires_service(...)` arguments.

    No args means the historical default: Ollama.
    """
    raw: list[object] = list(args)
    for key in ("service", "services"):
        value = kwargs.get(key)
        if isinstance(value, (list, tuple, set)):
            raw.extend(value)
        elif value:
            raw.append(value)
    if not raw:
        return ("ollama",)
    return tuple(str(v).strip().replace("-", "_") for v in raw if str(v).strip())


def http_ok(url: str, *, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 200 <= response.status < 500
    except Exception:
        return False


def tcp_ok(host: str, port: int, *, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except Exception:
        return False


def _ollama() -> ServiceStatus:
    base = os.environ.get("OLLAMA_BASE", "http://localhost:11434").rstrip("/")
    ok = http_ok(f"{base}/api/tags")
    return ServiceStatus("ollama", ok, f"Ollama offline em {base}")


def _milvus() -> ServiceStatus:
    uri = os.environ.get("MILVUS_URI")
    if uri:
        parsed = urlparse(uri)
        host = parsed.hostname or "localhost"
        port = parsed.port or 19530
        ok = tcp_ok(host, port)
        return ServiceStatus("milvus", ok, f"Milvus offline em {uri}")
    host = os.environ.get("MILVUS_HOST", "localhost")
    port = int(os.environ.get("MILVUS_PORT", "19530"))
    ok = tcp_ok(host, port)
    return ServiceStatus("milvus", ok, f"Milvus offline em {host}:{port}")


def _falkordb() -> ServiceStatus:
    host = os.environ.get("FALKORDB_HOST", "localhost")
    port = int(os.environ.get("FALKORDB_PORT", "6379"))
    ok = tcp_ok(host, port)
    return ServiceStatus("falkordb", ok, f"FalkorDB offline em {host}:{port}")


def _claude_mem() -> ServiceStatus:
    host = os.environ.get("CLAUDE_MEM_WORKER_HOST", "127.0.0.1")
    port = os.environ.get("CLAUDE_MEM_WORKER_PORT", "37700")
    url = f"http://{host}:{port}/api/health"
    if http_ok(url):
        return ServiceStatus("claude_mem", True, f"claude-mem worker online em {url}")

    db = Path(os.environ.get("CLAUDE_MEM_DB", str(Path.home() / ".claude-mem" / "claude-mem.db")))
    ok = db.exists()
    return ServiceStatus(
        "claude_mem",
        ok,
        f"claude-mem offline: worker {url} indisponivel e DB ausente em {db}",
    )


def _ragflow() -> ServiceStatus:
    base = os.environ.get("RAGFLOW_BASE", os.environ.get("RAGFLOW_API_URL", "http://localhost:9380")).rstrip("/")
    ok = http_ok(f"{base}/api/v1/system/healthz") or http_ok(f"{base}/api/v1/system/ping")
    return ServiceStatus("ragflow", ok, f"RAGFlow offline em {base}")


SERVICE_CHECKS = {
    "ollama": _ollama,
    "milvus": _milvus,
    "falkordb": _falkordb,
    "claude_mem": _claude_mem,
    "ragflow": _ragflow,
}


def check_service(name: str) -> ServiceStatus:
    normalized = name.strip().replace("-", "_")
    checker = SERVICE_CHECKS.get(normalized)
    if checker is None:
        known = ", ".join(sorted(SERVICE_CHECKS))
        return ServiceStatus(normalized, False, f"servico requires_service desconhecido: {normalized}; conhecidos: {known}", True)
    return checker()
