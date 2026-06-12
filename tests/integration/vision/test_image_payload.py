"""PATCH 1 payload — verifica que o conteúdo multipart enviado a um provedor
OpenAI-compat carrega a imagem como data URL (não foi descartada).

Captura requests.post via spy de baixo nível: o retorno é stubbed (não gastamos
tokens), mas o PAYLOAD enviado é o real, byte a byte. Decode do base64 e compara
com o PNG original.

Origem: /tmp/smoke_image.py
"""
import base64
import json
from pathlib import Path

import pytest

# PIL é opcional aqui — geramos o PNG via zlib no conftest. Mas o script
# original usava PIL. Mantemos este teste SEM PIL: usa o fixture vision_png.


def test_image_part_reaches_payload_as_data_url(saved_env, vision_png, monkeypatch):
    """Spy em requests.post: o body enviado ao provedor deve ter image_url com
    data URL cujo base64 decode bate com o PNG original."""
    import requests as real_requests
    from core.llm_client import call_llm_structured
    from pydantic import BaseModel

    class Out(BaseModel):
        ok: bool

    captured: list[dict] = []
    orig_post = real_requests.post

    def spy_post(url, *args, **kwargs):
        captured.append({"url": url, "json": kwargs.get("json"), "headers": kwargs.get("headers", {})})

        class FakeResp:
            ok = True
            status_code = 200
            text = '{"ok":true}'

            def json(self_inner):
                return {"choices": [{"message": {"content": '{"ok": true}'}}]}

        return FakeResp()

    monkeypatch.setattr(real_requests, "post", spy_post)
    try:
        out = call_llm_structured(
            prompt="What color is this?",
            system_prompt="You describe images.",
            response_model=Out,
            image_path=str(vision_png),
            provider="ollama",
            model="qwen3:8b",
        )
    finally:
        monkeypatch.setattr(real_requests, "post", orig_post)

    assert out.ok is True
    assert len(captured) >= 1, "request não chegou ao provedor"

    req = captured[0]
    body = req["json"]
    assert body is not None
    user_msg = body["messages"][1]
    content = user_msg["content"]
    assert isinstance(content, list), f"PATCH 1 falhou: content é {type(content).__name__}, não lista"
    kinds = [item.get("type") for item in content]
    assert "image_url" in kinds, f"image_url ausente. parts={kinds}"

    img_part = next(x for x in content if x.get("type") == "image_url")
    url = img_part["image_url"]["url"]
    assert url.startswith("data:"), f"esperava data URL, recebi prefixo: {url[:30]!r}"

    header, data = url.split(",", 1)
    decoded = base64.b64decode(data)
    assert decoded == vision_png.read_bytes(), "bytes decodados != PNG original"
    assert "image/png" in header or "image/jpeg" in header, f"MIME inesperado: {header}"
