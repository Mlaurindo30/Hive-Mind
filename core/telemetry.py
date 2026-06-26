"""Telemetria opcional via OpenTelemetry → Langfuse self-hosted."""
from __future__ import annotations

import os
import sys
import base64
from contextlib import contextmanager

_tracer = None
_enabled = False
_warned_missing_deps = False


def _langfuse_headers() -> dict:
    pk = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
    sk = os.environ.get("LANGFUSE_SECRET_KEY", "")
    if not pk or not sk:
        return {}
    token = base64.b64encode(f"{pk}:{sk}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


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
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        endpoint = os.environ.get("LANGFUSE_HOST", "http://localhost:3100")
        exporter = OTLPSpanExporter(
            endpoint=f"{endpoint}/api/public/otel/v1/traces",
            headers=headers,
        )
        provider = TracerProvider()
        provider.add_span_processor(BatchSpanProcessor(exporter))
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
    """Forca o flush do BatchSpanProcessor. No-op se telemetria desabilitada."""
    if not _enabled or _tracer is None:
        return
    try:
        _tracer.provider.force_flush()
    except Exception:
        pass


@contextmanager
def span(name: str, attributes: dict | None = None):
    """Context manager para criar um span OTEL. No-op se telemetria desabilitada."""
    if not _enabled or _tracer is None:
        yield None
        return
    with _tracer.start_as_current_span(name) as s:
        if attributes:
            for k, v in attributes.items():
                s.set_attribute(k, str(v))
        yield s
