"""Telemetria opcional via OpenTelemetry → Langfuse self-hosted."""
from __future__ import annotations

import os
import sys
import base64
from contextlib import contextmanager

_tracer = None
_enabled = False
_warned_missing_deps = False
_warned_flush_failed = False


def _langfuse_headers() -> dict:
    pk = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
    sk = os.environ.get("LANGFUSE_SECRET_KEY", "")
    if not pk or not sk:
        return {}
    # Strip whitespace malformado (pega `pk = os.environ.get(...).strip()`)
    pk = pk.strip()
    sk = sk.strip()
    token = base64.b64encode(f"{pk}:{sk}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _langfuse_endpoint() -> str:
    """Normaliza LANGFUSE_HOST removendo trailing slash antes de concatenar path."""
    host = os.environ.get("LANGFUSE_HOST", "http://localhost:3100").strip()
    # Segurança: avisa se HTTP (não HTTPS) E não for localhost (dev only)
    if host.startswith("http://") and not (
        "localhost" in host or "127.0.0.1" in host or "::1" in host
    ):
        global _warned_missing_deps
        if not _warned_missing_deps:
            print(
                f"[hive-mind] LANGFUSE_HOST usa HTTP (não HTTPS) em host não-local: "
                f"{host}. Basic auth + traces serão enviados em cleartext.",
                file=sys.stderr,
            )
            _warned_missing_deps = True  # reusa flag warn-once para evitar spam
    return host.rstrip("/") + "/api/public/otel/v1/traces"


def init_telemetry() -> bool:
    """Inicializa OTEL se LANGFUSE_PUBLIC_KEY estiver definido. Idempotente."""
    global _tracer, _enabled, _warned_missing_deps
    if _tracer is not None:
        return _enabled
    headers = _langfuse_headers()
    if not headers:
        return False
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        service_name = os.environ.get("HIVE_SERVICE_NAME", "hive-mind").strip()
        provider = TracerProvider(
            resource=Resource.create(
                {
                    "service.name": service_name,
                    "service.version": "3.0.0",
                }
            )
        )
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(
            endpoint=_langfuse_endpoint(),
            headers=headers,
        )))
        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer("hive-mind")
        _enabled = True
        return True
    except ImportError:
        if not _warned_missing_deps:
            print(
                "[hive-mind] LANGFUSE keys setadas mas opentelemetry-sdk nao "
                "instalado. Rode: uv sync",
                file=sys.stderr,
            )
            _warned_missing_deps = True
        return False


def flush_telemetry() -> None:
    """Forca o flush do TracerProvider (API canônica). No-op se telemetria desabilitada."""
    global _warned_flush_failed
    if not _enabled:
        return
    try:
        from opentelemetry import trace
        # API correta: force_flush(timeout_millis=...) está em TracerProvider,
        # NÃO em Tracer (a classe Tracer expõe apenas start_span). Warns-one
        # em stderr se o flush falhar (Langfuse down, OTLP proto bug, etc.).
        trace.get_tracer_provider().force_flush(timeout_millis=5000)
    except Exception as e:
        if not _warned_flush_failed:
            print(
                f"[hive-mind] flush_telemetry falhou: {type(e).__name__}: {e}",
                file=sys.stderr,
            )
            _warned_flush_failed = True


@contextmanager
def span(name: str, attributes: dict | None = None):
    """Context manager para criar um span OTEL. No-op se telemetria desabilitada.

    Quando desabilitado, `yield None` — callers que fizerem `s.set_attribute(...)`
    devem guardar (ex.: `if s is not None: s.set_attribute(...)`) ou simplesmente
    confiar no `with` que fecha o span sem efeito.
    """
    if not _enabled or _tracer is None:
        yield None
        return
    with _tracer.start_as_current_span(name) as s:
        if attributes:
            for k, v in attributes.items():
                # OTel aceita primitivos (bool, int, float, str, sequence[str]).
                # Coerce não-OTel types para str; preserva int/float/bool para
                # queries tipadas no Langfuse (ex.: budget_left<60).
                if isinstance(v, (bool, int, float, str)) or (
                    isinstance(v, list) and all(isinstance(x, str) for x in v)
                ):
                    s.set_attribute(k, v)
                else:
                    s.set_attribute(k, str(v))
        yield s
