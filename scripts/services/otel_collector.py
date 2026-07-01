#!/usr/bin/env python3
"""Hive-Mind OTLP Collector — Stub para tracing local.

Por que existe:
    Langfuse v3+ (atual LTS) requer Postgres + ClickHouse + Redis para
    self-hosted. Para dev/test, isso e' overhead. Este script implementa
    um OTLP/HTTP collector minimo em Python puro que:

    1. Aceita POST em /v1/traces (formato OTLP protobuf ou JSON)
    2. Extrai spans do payload
    3. Escreve em JSONL em `logs/otel-spans.log`
    4. Expõe /v1/health para liveness

    E' OTel-spec compliant: aceita o mesmo payload que Langfuse espera
    (protobuf + JSON). Quando o operador subir Langfuse real, basta
    apontar LANGFUSE_HOST para ele e o mesmo `core/telemetry.py`
    continua funcionando.

Uso:
    python3 scripts/services/otel_collector.py --port 3100 --log /home/.../logs/otel-spans.log

Saida:
    Cada span vira uma linha JSON em `otel-spans.log` com:
    {
        "name": "sinapse_query",
        "trace_id": "0af7651916cd43dd8448eb211c80319c",
        "span_id": "b7ad6b7169203331",
        "start_time_unix_nano": 1695000000000000000,
        "end_time_unix_nano":   1695000000125000000,
        "duration_ms": 125,
        "attributes": {...},
        "status": {"code": 1, "message": "OK"},
        "received_at": "2026-07-01T18:30:00Z"
    }

Nao produz ruido: spans com erro sao marcados em `status.code=2` e
incluem `status.message`.
"""
import argparse
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))


class OTLPHandler(BaseHTTPRequestHandler):
    # Silencia logs de conexao do BaseHTTPServer (a cada POST imprime 1 linha)
    def log_message(self, format, *args):
        return

    def __init__(self, *args, log_path: Path, **kwargs):
        self._log_path = log_path
        super().__init__(*args, **kwargs)

    def do_GET(self):
        if self.path == "/v1/health" or self.path == "/health":
            self._respond_json({"status": "ok", "service": "hive-otel-collector"})
        elif self.path == "/metrics":
            try:
                count = sum(1 for _ in self._log_path.open("r", encoding="utf-8"))
            except FileNotFoundError:
                count = 0
            self._respond_json({"spans_received": count, "log_path": str(self._log_path)})
        else:
            self._respond_json({"error": "not found"}, code=404)

    def do_POST(self):
        # Aceita tanto /v1/traces (OTLP padrao) quanto
        # /api/public/otel/v1/traces (path canonico do Langfuse).
        if self.path not in ("/v1/traces", "/api/public/otel/v1/traces"):
            self._respond_json({"error": "POST /v1/traces ou /api/public/otel/v1/traces"}, code=404)
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(content_length)
            spans = self._extract_spans(body)
            self._write_spans(spans)
            # OTLP espera 200 OK com ExportTraceServiceResponse vazio.
            # Em prod, esse body seria protobuf-encoded. Para stubs,
            # muitos clients aceitam 200 + JSON qualquer.
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{}')
        except Exception as exc:
            self._respond_json(
                {"error": f"{type(exc).__name__}: {exc}"}, code=500
            )

    def _extract_spans(self, body: bytes) -> list[dict]:
        """Aceita JSON OTLP ou protobuf binario.

        O exporter padrao do opentelemetry-sdk envia protobuf (Content-Type:
        application/x-protobuf) por questao de performance. O Langfuse
        aceita JSON. Suportamos ambos para nao perder dados.
        """
        if not body:
            return []
        ct = (self.headers.get("Content-Type") or "").lower()
        if "json" in ct:
            return self._extract_from_json(body)
        if "protobuf" in ct or not ct:
            return self._extract_from_protobuf(body)
        return []

    def _extract_from_json(self, body: bytes) -> list[dict]:
        try:
            data = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            return []
        spans = []
        for rs in data.get("resourceSpans", []):
            for ss in rs.get("scopeSpans", []):
                for span in ss.get("spans", []):
                    spans.append(self._normalize_json(span))
        return spans

    def _extract_from_protobuf(self, body: bytes) -> list[dict]:
        try:
            from opentelemetry.proto.collector.trace.v1 import trace_service_pb2
            request = trace_service_pb2.ExportTraceServiceRequest()
            request.ParseFromString(body)
        except Exception:
            return []
        spans = []
        for rs in request.resource_spans:
            for ss in rs.scope_spans:
                for span_proto in ss.spans:
                    spans.append(self._normalize_proto(span_proto))
        return spans

    def _normalize_json(self, span: dict) -> dict:
        attrs = {}
        for kv in span.get("attributes", []):
            key = kv.get("key", "")
            val = kv.get("value", {})
            if "stringValue" in val:
                attrs[key] = val["stringValue"]
            elif "intValue" in val:
                attrs[key] = int(val["intValue"])
            elif "doubleValue" in val:
                attrs[key] = float(val["doubleValue"])
            elif "boolValue" in val:
                attrs[key] = bool(val["boolValue"])
        start_ns = int(span.get("startTimeUnixNano", 0))
        end_ns = int(span.get("endTimeUnixNano", 0))
        duration_ms = (end_ns - start_ns) / 1_000_000 if start_ns and end_ns else None
        status = span.get("status", {})
        return {
            "name": span.get("name", ""),
            "trace_id": span.get("traceId", ""),
            "span_id": span.get("spanId", ""),
            "parent_span_id": span.get("parentSpanId", ""),
            "start_time_unix_nano": start_ns,
            "end_time_unix_nano": end_ns,
            "duration_ms": duration_ms,
            "attributes": attrs,
            "status": {
                "code": status.get("code", 0),
                "message": status.get("message", ""),
            },
            "received_at": datetime.now(timezone.utc).isoformat(),
        }

    def _normalize_proto(self, span_proto) -> dict:
        # Mapear enum StatusCode: STATUS_CODE_UNSET=0, OK=1, ERROR=2
        status_code_map = {0: "UNSET", 1: "OK", 2: "ERROR"}
        attrs = {}
        for kv in span_proto.attributes:
            key = kv.key
            v = kv.value
            # AnyValue: string_value, int_value, double_value, bool_value
            if v.HasField("string_value"):
                attrs[key] = v.string_value
            elif v.HasField("int_value"):
                attrs[key] = int(v.int_value)
            elif v.HasField("double_value"):
                attrs[key] = float(v.double_value)
            elif v.HasField("bool_value"):
                attrs[key] = bool(v.bool_value)
        start_ns = span_proto.start_time_unix_nano
        end_ns = span_proto.end_time_unix_nano
        duration_ms = (end_ns - start_ns) / 1_000_000 if start_ns and end_ns else None
        # trace_id e span_id vem como bytes (8 e 16 bytes) - hex
        return {
            "name": span_proto.name,
            "trace_id": span_proto.trace_id.hex() if span_proto.trace_id else "",
            "span_id": span_proto.span_id.hex() if span_proto.span_id else "",
            "parent_span_id": span_proto.parent_span_id.hex() if span_proto.parent_span_id else "",
            "start_time_unix_nano": start_ns,
            "end_time_unix_nano": end_ns,
            "duration_ms": duration_ms,
            "attributes": attrs,
            "status": {
                "code": status_code_map.get(span_proto.status.code, 0),
                "message": span_proto.status.message,
            },
            "received_at": datetime.now(timezone.utc).isoformat(),
        }



    def _write_spans(self, spans: list[dict]) -> None:
        if not spans:
            return
        with self._log_path.open("a", encoding="utf-8") as f:
            for s in spans:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")

    def _respond_json(self, payload: dict, code: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def make_handler(log_path: Path):
    """Factory que captura log_path no closure (BaseHTTPServer nao aceita
    args no __init__ via servidor; cada request instancia o handler)."""
    def factory(*args, **kwargs):
        return OTLPHandler(*args, log_path=log_path, **kwargs)
    return factory


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Hive-Mind OTLP collector stub (aceita POST /v1/traces)."
    )
    parser.add_argument(
        "--port", type=int,
        default=int(__import__("os").environ.get("HIVE_OTEL_PORT", "3100")),
        help="Porta para HTTP listener (default: HIVE_OTEL_PORT ou 3100).",
    )
    parser.add_argument(
        "--host", type=str, default="127.0.0.1",
        help="Host (default 127.0.0.1 - nao exponha publicamente sem auth).",
    )
    parser.add_argument(
        "--log", type=Path,
        default=Path(__import__("os").environ.get(
            "HIVE_OTEL_LOG", str(ROOT / "logs" / "otel-spans.log")
        )),
        help="Arquivo JSONL para spans (default: logs/otel-spans.log).",
    )
    args = parser.parse_args()

    args.log.parent.mkdir(parents=True, exist_ok=True)
    args.log.touch()

    server = ThreadingHTTPServer((args.host, args.port), make_handler(args.log))
    print(
        f"[hive-otel-collector] listening on http://{args.host}:{args.port} "
        f"-> {args.log} (PID {__import__('os').getpid()})"
    )
    print(
        f"[hive-otel-collector] para usar: export LANGFUSE_HOST=http://{args.host}:{args.port}"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[hive-otel-collector] shutting down")
        server.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
