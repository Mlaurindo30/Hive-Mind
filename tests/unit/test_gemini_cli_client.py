"""Provider gemini-cli (Code Assist) — envelope, parsing e classificação de erro.

Mocka a rede (requests.post) e os helpers de token/projeto: valida que o request vai
no envelope Code Assist correto e que a resposta é parseada no response_model. Sem rede.
"""
import sys
import types
from pathlib import Path

import pytest
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import gemini_cli_client as gc


class Fato(BaseModel):
    resumo: str
    confianca: float


class _Resp:
    def __init__(self, status, payload=None, text=""):
        self.status_code = status
        self._payload = payload or {}
        self.text = text
    @property
    def ok(self):
        return 200 <= self.status_code < 300
    def json(self):
        return self._payload


def _patch_auth(monkeypatch):
    monkeypatch.setattr(gc, "get_access_token", lambda: "tok-123")
    monkeypatch.setattr(gc, "get_project_id", lambda token, endpoint=None: "proj-x")


def test_extract_text_shape():
    data = {"response": {"candidates": [{"content": {"parts": [{"text": "a"}, {"text": "b"}]}}]}}
    assert gc._extract_text(data) == "ab"


def test_envelope_e_parsing(monkeypatch):
    _patch_auth(monkeypatch)
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["body"] = json
        captured["auth"] = headers["Authorization"]
        text = '{"resumo": "céu azul", "confianca": 0.9}'
        return _Resp(200, {"response": {"candidates": [{"content": {"parts": [{"text": text}]}}]}})

    monkeypatch.setattr(gc.requests, "post", fake_post)
    out = gc.call_gemini_cli_structured("p", "sys", Fato, model="gemini-2.5-flash")
    assert isinstance(out, Fato) and out.confianca == 0.9
    # envelope Code Assist correto
    assert captured["url"].endswith("/v1internal:generateContent")
    assert captured["body"]["model"] == "gemini-2.5-flash"
    assert captured["body"]["project"] == "proj-x"
    assert "contents" in captured["body"]["request"]
    assert captured["body"]["request"]["generationConfig"]["responseMimeType"] == "application/json"
    assert captured["auth"] == "Bearer tok-123"


def test_403_vira_erro_de_auth_classificavel(monkeypatch):
    _patch_auth(monkeypatch)
    monkeypatch.setattr(gc.requests, "post",
                        lambda *a, **k: _Resp(403, text="scope insufficient"))
    with pytest.raises(gc.GeminiCliError) as exc:
        gc.call_gemini_cli_structured("p", "sys", Fato, model="gemini-2.5-flash")
    # mensagem contém 'authentication failed' → call_llm_with_fallback trata como auth
    assert "authentication failed" in str(exc.value).lower()


def test_5xx_vira_erro_generico(monkeypatch):
    _patch_auth(monkeypatch)
    monkeypatch.setattr(gc.requests, "post", lambda *a, **k: _Resp(503, text="unavailable"))
    with pytest.raises(gc.GeminiCliError) as exc:
        gc.call_gemini_cli_structured("p", "sys", Fato, model="gemini-2.5-flash")
    assert "503" in str(exc.value)


def test_llm_client_dispatch_para_gemini_cli(monkeypatch):
    """call_llm_structured(provider='gemini-cli') deve rotear p/ o módulo Code Assist."""
    import core.llm_client as llm
    called = {}
    def fake(prompt, system_prompt, response_model, model, image_path=None, provider=None):
        called["hit"] = (model, provider)
        return Fato(resumo="ok", confianca=1.0)
    monkeypatch.setattr("core.gemini_cli_client.call_gemini_cli_structured", fake)
    out = llm.call_llm_structured("p", "s", Fato, provider="gemini-cli", model="gemini-2.5-flash")
    assert out.resumo == "ok" and called["hit"][0] == "gemini-2.5-flash"


# --- saneamento de schema (Code Assist não aceita $defs/$ref) -----------------
def test_to_gemini_schema_inline_refs_e_remove_defs():
    raw = {
        "$defs": {"Fact": {"type": "object", "title": "Fact",
                            "properties": {"x": {"type": "string", "default": "a"}}}},
        "type": "object",
        "title": "Out",
        "properties": {
            "facts": {"type": "array", "items": {"$ref": "#/$defs/Fact"}},
            "opt": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        },
        "additionalProperties": False,
    }
    clean = gc._to_gemini_schema(raw)
    import json as _j
    blob = _j.dumps(clean)
    assert "$defs" not in blob and "$ref" not in blob          # inlined
    assert "title" not in blob and "default" not in blob        # removidos
    assert "additionalProperties" not in blob
    # $ref de Fact foi inlined no items
    assert clean["properties"]["facts"]["items"]["type"] == "object"
    # Optional → nullable
    assert clean["properties"]["opt"]["type"] == "string"
    assert clean["properties"]["opt"]["nullable"] is True


def test_endpoint_por_provider(monkeypatch):
    # antigravity deixou de ser provider Code Assist aqui (migrou p/ core.agy_client);
    # este cliente só fala cloudcode-pa (gemini-cli / code-assist). O default também
    # é cloudcode-pa (não mais o daily- do antigravity).
    monkeypatch.delenv("GEMINI_CLI_ENDPOINT", raising=False)
    assert gc._endpoint_for("gemini-cli").endswith("cloudcode-pa.googleapis.com")
    assert gc._endpoint_for("code-assist").endswith("cloudcode-pa.googleapis.com")
    assert "daily-cloudcode-pa" not in gc._endpoint_for("gemini-cli")
    assert "daily-cloudcode-pa" not in gc._endpoint_for(None)   # default = cloudcode-pa


def test_env_override_endpoint(monkeypatch):
    monkeypatch.setenv("GEMINI_CLI_ENDPOINT", "https://x.example.com")
    assert gc._endpoint_for("gemini-cli") == "https://x.example.com"


def test_call_usa_endpoint_do_provider(monkeypatch):
    _patch_auth(monkeypatch)
    monkeypatch.delenv("GEMINI_CLI_ENDPOINT", raising=False)
    captured = {}
    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        text = '{"resumo":"x","confianca":0.5}'
        return _Resp(200, {"response": {"candidates": [{"content": {"parts": [{"text": text}]}}]}})
    monkeypatch.setattr(gc.requests, "post", fake_post)
    gc.call_gemini_cli_structured("p", "s", Fato, model="gemini-2.5-flash", provider="gemini-cli")
    assert "cloudcode-pa.googleapis.com" in captured["url"] and "daily-" not in captured["url"]


def test_model_chain_rotaciona():
    chain = gc._model_chain("gemini-cli", "gemini-2.5-flash")
    assert chain[0] == "gemini-2.5-flash"           # pedido primeiro
    assert "gemini-3.1-pro-preview" in chain        # demais do provider (3.x -preview)
    assert chain.count("gemini-2.5-flash") == 1     # sem duplicar


def test_429_rotaciona_para_proximo_modelo(monkeypatch):
    _patch_auth(monkeypatch)
    monkeypatch.delenv("GEMINI_CLI_ENDPOINT", raising=False)
    calls = []
    def fake_post(url, headers=None, json=None, timeout=None):
        m = json["model"]; calls.append(m)
        if m == "gemini-2.5-flash":        # 1º modelo: rate-limited
            return _Resp(429, text="exhausted on this model")
        text = '{"resumo":"ok","confianca":1.0}'
        return _Resp(200, {"response": {"candidates": [{"content": {"parts": [{"text": text}]}}]}})
    monkeypatch.setattr(gc.requests, "post", fake_post)
    out = gc.call_gemini_cli_structured("p", "s", Fato, model="gemini-2.5-flash", provider="gemini-cli")
    assert out.resumo == "ok"
    # rotaciona p/ o próximo da cadeia gemini-cli (gemini-3.1-flash-lite)
    assert calls[0] == "gemini-2.5-flash" and calls[1] == "gemini-3.1-flash-lite"


def test_todos_modelos_429_levanta_transient(monkeypatch):
    _patch_auth(monkeypatch)
    monkeypatch.setattr(gc.requests, "post", lambda *a, **k: _Resp(429, text="exhausted"))
    with pytest.raises(gc.GeminiCliError) as exc:
        gc.call_gemini_cli_structured("p", "s", Fato, model="gemini-2.5-flash", provider="gemini-cli")
    assert "429" in str(exc.value)   # classificado transient → fallback do papel
