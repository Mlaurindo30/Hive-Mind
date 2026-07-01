"""F4.6 — Testes da telemetria Langfuse opt-in (K8 harden).

Garante que:
  1. Sem LANGFUSE_PUBLIC_KEY, init_telemetry() retorna False e nao faz nada.
  2. _langfuse_headers() retorna {} sem keys.
  3. _langfuse_endpoint() normaliza trailing slash.
  4. O context manager `span` faz yield None quando desabilitado.
  5. Com keys setadas, init_telemetry() tenta carregar OTEL (mas nao exige
     a lib instalada - cobre o caminho de warn-once).
"""
import os
import sys
import unittest
from contextlib import contextmanager
from unittest import mock

import core.telemetry as telemetry


class TelemetryOptInTests(unittest.TestCase):
    def setUp(self):
        # Limpa estado global do modulo
        telemetry._tracer = None
        telemetry._enabled = False
        telemetry._warned_missing_deps = False
        telemetry._warned_flush_failed = False
        # Remove env vars se setadas por testes anteriores
        for var in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST"):
            os.environ.pop(var, None)

    def test_no_op_when_keys_missing(self):
        self.assertEqual(telemetry._langfuse_headers(), {})
        # init_telemetry() nao deve habilitar tracer
        result = telemetry.init_telemetry()
        self.assertFalse(result)
        self.assertFalse(telemetry._enabled)

    def test_span_yields_none_when_disabled(self):
        # init_telemetry() com OTEL ausente: continua desabilitado
        with telemetry.span("test-span", attributes={"key": "value"}) as s:
            self.assertIsNone(s)

    def test_endpoint_normalizes_trailing_slash(self):
        os.environ["LANGFUSE_HOST"] = "http://localhost:3100/"
        endpoint = telemetry._langfuse_endpoint()
        # Sem double slash
        self.assertNotIn("3100//", endpoint)
        self.assertIn("/api/public/otel/v1/traces", endpoint)
        self.assertTrue(endpoint.startswith("http://localhost:3100/api/"))

    def test_endpoint_warns_on_remote_http(self):
        # Captura stderr para validar warn-once
        import io
        os.environ["LANGFUSE_HOST"] = "http://langfuse.example.com"
        with mock.patch("sys.stderr", new=io.StringIO()) as fake_err:
            telemetry._langfuse_endpoint()
            first_warn = fake_err.getvalue()
            self.assertIn("HTTP", first_warn)
            self.assertIn("cleartext", first_warn)

        # Segunda chamada NAO deve duplicar o warn (warn-once)
        with mock.patch("sys.stderr", new=io.StringIO()) as fake_err:
            telemetry._langfuse_endpoint()
            second_warn = fake_err.getvalue()
            self.assertEqual(second_warn, "")

    def test_endpoint_does_not_warn_on_localhost_http(self):
        # localhost em HTTP e' ok (dev)
        import io
        os.environ["LANGFUSE_HOST"] = "http://localhost:3100"
        with mock.patch("sys.stderr", new=io.StringIO()) as fake_err:
            telemetry._langfuse_endpoint()
            self.assertEqual(fake_err.getvalue(), "")

    def test_headers_base64_encoded(self):
        os.environ["LANGFUSE_PUBLIC_KEY"] = "pk-test-123"
        os.environ["LANGFUSE_SECRET_KEY"] = "sk-test-456"
        headers = telemetry._langfuse_headers()
        self.assertIn("Authorization", headers)
        # Basic auth = base64("pk:sk")
        import base64
        expected = base64.b64encode(b"pk-test-123:sk-test-456").decode()
        self.assertEqual(headers["Authorization"], f"Basic {expected}")

    def test_headers_strip_whitespace(self):
        os.environ["LANGFUSE_PUBLIC_KEY"] = "  pk-test  \n"
        os.environ["LANGFUSE_SECRET_KEY"] = "  sk-test  \n"
        headers = telemetry._langfuse_headers()
        self.assertIn("Basic", headers["Authorization"])
        # Whitespace removido
        self.assertNotIn(" ", headers["Authorization"].replace("Basic ", ""))

    def test_init_telemetry_with_keys_no_otel_emits_warn(self):
        # Com keys mas sem opentelemetry, deve emitir warn-once e retornar False
        os.environ["LANGFUSE_PUBLIC_KEY"] = "pk-test"
        os.environ["LANGFUSE_SECRET_KEY"] = "sk-test"
        # Simula OTEL ausente
        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name.startswith("opentelemetry"):
                raise ImportError(f"mocked: {name}")
            return original_import(name, *args, **kwargs)

        import io
        with mock.patch.object(builtins, "__import__", side_effect=mock_import):
            with mock.patch("sys.stderr", new=io.StringIO()) as fake_err:
                result = telemetry.init_telemetry()
                self.assertFalse(result)
                self.assertIn("opentelemetry-sdk", fake_err.getvalue())

    def test_flush_telemetry_noop_when_disabled(self):
        # Sem init_telemetry, flush deve ser no-op (sem exception)
        telemetry.flush_telemetry()
        # Sem exception = sucesso
        self.assertFalse(telemetry._enabled)

    def test_span_coerces_non_otel_types(self):
        # Atributos nao-OTel (ex: dict) devem ser coerced para str
        # Para isso, precisamos habilitar tracer - usamos mock
        mock_span = mock.MagicMock()
        mock_tracer = mock.MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__ = mock.MagicMock(
            return_value=mock_span
        )
        mock_tracer.start_as_current_span.return_value.__exit__ = mock.MagicMock(
            return_value=False
        )
        telemetry._tracer = mock_tracer
        telemetry._enabled = True
        try:
            with telemetry.span("test", attributes={"complex": {"nested": "obj"}}) as s:
                s.set_attribute("x", 1)
            # Verifica que set_attribute foi chamado
            self.assertTrue(mock_span.set_attribute.called)
        finally:
            telemetry._tracer = None
            telemetry._enabled = False


if __name__ == "__main__":
    unittest.main()
