"""P9 - Testes de instrumentacao OpenTelemetry (Langfuse opt-in).

Usa InMemorySpanProcessor real do OTel SDK (sem mocks, sem Langfuse rodando).
Reset do estado global de core.telemetry antes de cada teste para evitar vazamento.
"""
import os
import sys
import io
import pytest


def _reset_otel_singleton():
    """Reseta o singleton global TracerProvider do OTel SDK.

    OTel SDK usa sync.Once interno para garantir set_tracer_provider seja
    idempotente. Para testes, precisamos resetar _done=True -> False para
    permitir setar novamente, alem de chamar _set_tracer_provider(None).
    """
    try:
        from opentelemetry import trace
        # 1. Limpa a referencia para o provider
        if hasattr(trace, "_set_tracer_provider"):
            trace._set_tracer_provider(None, log=False)
        # 2. Reseta o flag do sync.Once (permite re-setar)
        if hasattr(trace, "_TRACER_PROVIDER_SET_ONCE"):
            once = trace._TRACER_PROVIDER_SET_ONCE
            if hasattr(once, "_done"):
                once._done = False
        # 3. Limpa o cache do proxy tracer
        if hasattr(trace, "_TRACER_PROVIDER"):
            trace._TRACER_PROVIDER = None
        if hasattr(trace, "_PROXY_TRACER_PROVIDER"):
            trace._PROXY_TRACER_PROVIDER = None
    except Exception:
        pass


@pytest.fixture(autouse=True)
def reset_telemetry_state(monkeypatch):
    """Reseta _tracer/_enabled/_warned_missing_deps + TracerProvider global OTel.

    O OTel SDK so permite setar TracerProvider uma vez por processo. Para
    testes consecutivos funcionarem, resetamos via _set_tracer_provider
    + sync.Once._done flag antes de cada teste.
    """
    import core.telemetry as t
    t._tracer = None
    t._enabled = False
    t._warned_missing_deps = False
    _reset_otel_singleton()
    for k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST"):
        monkeypatch.delenv(k, raising=False)
    yield
    import core.telemetry as t2
    t2._tracer = None
    t2._enabled = False
    t2._warned_missing_deps = False
    _reset_otel_singleton()


from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult


class _ListSpanExporter(SpanExporter):
    """Exporter real do OTel SDK que captura spans em lista (sem rede, sem mock).

    Subclasse de SpanExporter (API publica do OTel) — nao eh mock, eh um
    exporter legitimo como ConsoleSpanExporter, so que em memoria.
    """
    def __init__(self):
        self._spans = []

    def export(self, spans):
        self._spans.extend(spans)
        return SpanExportResult.SUCCESS

    def shutdown(self):
        pass

    @property
    def spans(self):
        return self._spans


def _enable_telemetry_with_memory_processor(monkeypatch):
    """Inicializa init_telemetry() com keys fake e injeta _ListSpanExporter."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_HOST", "http://localhost:9999")
    import core.telemetry as t
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry import trace
    exporter = _ListSpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    t._tracer = trace.get_tracer("hive-mind-test")
    t._enabled = True
    return exporter


def _spans(exporter):
    return exporter.spans


# 1. No-op quando desabilitado
def test_span_noop_when_disabled():
    from core.telemetry import span
    with span("x") as s:
        assert s is None


# 2. Span criado quando habilitado
def test_span_creates_span_when_enabled(monkeypatch):
    exporter = _enable_telemetry_with_memory_processor(monkeypatch)
    from core.telemetry import span
    with span("test.op", {"k": "v"}) as s:
        assert s is not None
    spans = _spans(exporter)
    assert len(spans) == 1
    assert spans[0].name == "test.op"
    assert spans[0].attributes["k"] == "v"


# 3. init_telemetry idempotente
def test_init_telemetry_idempotent(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    import core.telemetry as t
    ok1 = t.init_telemetry()
    tracer1 = t._tracer
    ok2 = t.init_telemetry()
    tracer2 = t._tracer
    assert ok1 is True and ok2 is True
    assert tracer1 is tracer2


# 4. Warning em deps faltando
def test_init_telemetry_warns_on_missing_deps(monkeypatch, capsys):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    for mod in list(sys.modules):
        if mod.startswith("opentelemetry"):
            monkeypatch.delitem(sys.modules, mod, raising=False)
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("opentelemetry"):
            raise ImportError(f"simulated: {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    import core.telemetry as t
    t._warned_missing_deps = False
    result = t.init_telemetry()
    assert result is False
    captured = capsys.readouterr()
    assert "opentelemetry-sdk" in captured.err
    assert "uv sync" in captured.err


# 5. flush no-op quando desabilitado
def test_flush_telemetry_noop_when_disabled():
    from core.telemetry import flush_telemetry
    flush_telemetry()


# 6. dream_cycle cria spans (LLM mockado)
def test_dream_cycle_creates_spans(monkeypatch):
    pytest.importorskip("scripts.dream.dream_cycle")
    exporter = _enable_telemetry_with_memory_processor(monkeypatch)
    import scripts.dream.dream_cycle as dc

    monkeypatch.setattr(dc, "run_visual_dream_stage", lambda: None)
    monkeypatch.setattr(dc, "run_synthesis_cycle", lambda **kw: None)
    monkeypatch.setattr(dc, "agent_distill_and_validate", lambda logs: (None, "empty"))
    monkeypatch.setattr(dc, "_route_and_persist_project", lambda *a, **kw: 0)
    monkeypatch.setattr(dc, "fetch_balanced_observations", lambda conn: [
        {"id": "x1", "type": "note", "title": "t", "content": "c", "project": "Test"}
    ])
    import types
    fake_mod = types.ModuleType("scripts.knowledge.document_ingest")
    fake_mod.run_ingestion = lambda: None
    monkeypatch.setitem(sys.modules, "scripts.knowledge.document_ingest", fake_mod)

    class FakeConn:
        def execute(self, *a, **kw): return None
        def commit(self): pass
        def close(self): pass
    monkeypatch.setattr(dc, "get_connection", lambda: FakeConn())
    monkeypatch.setattr(dc, "ensure_migrations", lambda c: None)

    dc._run_dream_cycle_inner()
    spans = _spans(exporter)
    names = [s.name for s in spans]
    assert "dream.document_ingest" in names
    assert "dream.visual" in names
    assert "dream.distill" in names


# 7. mcp handle_request cria span
def test_mcp_handle_request_creates_span(monkeypatch):
    exporter = _enable_telemetry_with_memory_processor(monkeypatch)
    import importlib.util
    plugin_path = os.path.join(
        os.path.dirname(__file__), "..", "..",
        "scripts", "services", "sinapse-mcp.py"
    )
    spec = importlib.util.spec_from_file_location("sinapse_mcp_test", plugin_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    mod.HANDLERS["__test_tool__"] = lambda args: {"ok": True}
    req = {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "__test_tool__", "arguments": {}},
    }
    resp = mod.handle_request(req)
    assert resp is not None
    spans = _spans(exporter)
    names = [s.name for s in spans]
    assert "mcp.__test_tool__" in names
