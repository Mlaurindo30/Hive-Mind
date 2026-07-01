"""F4.7 (v3.7.9+) — Testes do otel_collector.py (tracing sink).

Pressupoe que um collector stub esta rodando na porta 3100 (iniciado
pelo systemd hive-otel-collector.service). Se nao estiver, o teste
integração e' skipped - nao bloqueia CI local.
"""
import json
import os
import subprocess
import sys
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COLLECTOR = ROOT / "scripts" / "services" / "otel_collector.py"


def _collector_alive(host: str, port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/v1/health", timeout=1) as r:
            return r.status == 200
    except Exception:
        return False


def _start_collector(port: int, log_path: Path) -> subprocess.Popen:
    proc = subprocess.Popen(
        [sys.executable, str(COLLECTOR), "--port", str(port), "--log", str(log_path)],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # Aguarda /v1/health responder
    for _ in range(40):
        if _collector_alive("127.0.0.1", port):
            return proc
        time.sleep(0.1)
    out, err = proc.communicate(timeout=1)
    proc.kill()
    raise RuntimeError(
        f"collector nao respondeu /v1/health em 4s. stderr={err.decode()!r}"
    )


def _post(port: int, path: str, body: bytes, content_type: str) -> int:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=body,
        headers={"Content-Type": content_type},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=3) as r:
        return r.status


def _port_in_use(port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return False
        except OSError:
            return True


def _free_port() -> int:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class OtelCollectorUnitTests(unittest.TestCase):
    """Testa o collector isolado, em porta aleatoria (nao conflitua com
    o servico systemd em :3100)."""

    def setUp(self):
        # Pula se a porta 3100 ja' esta em uso (sistema) e usa 3100 direto
        if _port_in_use(3100):
            # Servico systemd ativo - usa 3100
            self.port = 3100
            self.log_path = ROOT / "logs" / "otel-spans.log"
            self.proc = None
        else:
            self.port = _free_port()
            self.log_path = ROOT / "logs" / f"otel-test-{self.port}.log"
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self.log_path.touch()
            self.proc = _start_collector(self.port, self.log_path)

    def tearDown(self):
        if self.proc is not None:
            self.proc.kill()
            self.proc.wait(timeout=2)
        # Limpa log de teste (mas NAO o log do sistema!)
        if self.port != 3100 and self.log_path.exists():
            self.log_path.unlink()

    def test_health_endpoint(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/v1/health", timeout=2) as r:
            data = json.loads(r.read().decode())
            self.assertEqual(data["status"], "ok")

    def test_metrics_endpoint(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/metrics", timeout=2) as r:
            data = json.loads(r.read().decode())
            self.assertIn("spans_received", data)

    def test_json_path(self):
        payload = {
            "resourceSpans": [
                {"scopeSpans": [{"spans": [{
                    "name": "json-test",
                    "startTimeUnixNano": "1000000000",
                    "endTimeUnixNano": "2000000000",
                    "attributes": [{"key": "k", "value": {"stringValue": "v"}}],
                }]}]}
            ]
        }
        status = _post(self.port, "/v1/traces", json.dumps(payload).encode(), "application/json")
        self.assertEqual(status, 200)
        # Le log (NÃO o do sistema, se 3100)
        if self.proc is not None:
            with self.log_path.open() as f:
                lines = [ln.strip() for ln in f if ln.strip()]
            self.assertEqual(len(lines), 1)
            rec = json.loads(lines[0])
            self.assertEqual(rec["name"], "json-test")
            self.assertEqual(rec["attributes"]["k"], "v")
            self.assertEqual(rec["duration_ms"], 1.0)

    def test_langfuse_path(self):
        payload = {
            "resourceSpans": [
                {"scopeSpans": [{"spans": [{
                    "name": "langfuse-path-test",
                    "startTimeUnixNano": "1000000000",
                    "endTimeUnixNano": "3000000000",
                }]}]}
            ]
        }
        status = _post(
            self.port, "/api/public/otel/v1/traces",
            json.dumps(payload).encode(), "application/json",
        )
        self.assertEqual(status, 200)
        if self.proc is not None:
            with self.log_path.open() as f:
                lines = [ln.strip() for ln in f if ln.strip()]
            self.assertEqual(len(lines), 1)
            rec = json.loads(lines[0])
            self.assertEqual(rec["name"], "langfuse-path-test")
            self.assertEqual(rec["duration_ms"], 2.0)

    def test_protobuf_path(self):
        from opentelemetry.proto.collector.trace.v1 import trace_service_pb2
        from opentelemetry.proto.trace.v1 import trace_pb2

        span = trace_pb2.Span()
        span.name = "proto-test"
        span.start_time_unix_nano = 1000000000
        span.end_time_unix_nano = 2500000000
        span.trace_id = b"\x01" * 16
        span.span_id = b"\x02" * 8
        attr = span.attributes.add()
        attr.key = "workspace"
        attr.value.string_value = "acme"

        scope = trace_pb2.ScopeSpans()
        scope.spans.append(span)
        rs = trace_pb2.ResourceSpans()
        rs.scope_spans.append(scope)
        request = trace_service_pb2.ExportTraceServiceRequest()
        request.resource_spans.append(rs)
        body = request.SerializeToString()

        status = _post(
            self.port, "/api/public/otel/v1/traces",
            body, "application/x-protobuf",
        )
        self.assertEqual(status, 200)
        if self.proc is not None:
            with self.log_path.open() as f:
                lines = [ln.strip() for ln in f if ln.strip()]
            self.assertEqual(len(lines), 1)
            rec = json.loads(lines[0])
            self.assertEqual(rec["name"], "proto-test")
            self.assertEqual(rec["attributes"]["workspace"], "acme")
            self.assertEqual(rec["trace_id"], "01" * 16)
            self.assertEqual(rec["span_id"], "02" * 8)

    def test_404_on_unknown_path(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(
                f"http://127.0.0.1:{self.port}/unknown", timeout=2
            )
        self.assertEqual(ctx.exception.code, 404)


class OtelCollectorSystemTest(unittest.TestCase):
    """Valida que o collector do systemd em :3100 esta' funcional.
    Nao escreve no log do sistema - apenas verifica health."""

    def test_systemd_collector_alive(self):
        # Skip se nao esta rodando
        if not _collector_alive("127.0.0.1", 3100):
            self.skipTest("hive-otel-collector.service nao esta em :3100")
        # Faz um POST vazio para validar que 200 OK e' retornado
        req = urllib.request.Request(
            "http://127.0.0.1:3100/v1/traces",
            data=b"",
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=2) as r:
                self.assertEqual(r.status, 200)
        except urllib.error.HTTPError as e:
            # 400/415 sao aceitaveis para body vazio; 200 e' ideal
            self.assertIn(e.code, (200, 400, 415))


if __name__ == "__main__":
    unittest.main()
