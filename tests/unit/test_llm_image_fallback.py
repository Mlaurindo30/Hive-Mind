"""
Testes para PATCH 1 do LLM Council — fallback de imagem no branch
OpenAI-compatible de ``core.llm_client.call_llm_structured``.

Cobre:
- Quando ``image_path`` é fornecido e o provider NÃO é Google/Gemini,
  a mensagem do usuário vira uma lista ``[{text}, {image_url}]`` com
  data URL no formato ``data:<mime>;base64,<...>`` (OpenAI Vision spec).
- A detecção de MIME respeita a extensão do arquivo (.png, .jpg,
  .jpeg, .gif, .webp) e cai num default seguro para extensões
  desconhecidas.
- Quando ``image_path`` é None, o conteúdo da mensagem do usuário
  continua sendo uma string (paridade com o comportamento anterior).

Sem chamadas reais a LLM: ``requests.post`` é mockado e capturamos o
payload enviado.
"""
import base64
import unittest.mock as mock

import pytest
from pydantic import BaseModel

from core import llm_client


class _SampleModel(BaseModel):
    """Modelo Pydantic mínimo para satisfazer o JSON Schema do caller."""
    title: str


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_png(tmp_path):
    """PNG mínimo de 1x1 pixel escrito em tmp_path."""
    # 1x1 transparent PNG (8 bytes header + IHDR + IDAT + IEND)
    png_bytes = bytes.fromhex(
        "89504E470D0A1A0A"  # PNG signature
        "0000000D49484452"  # IHDR length+name
        "0000000100000001"  # width=1, height=1
        "08060000001F15C489"  # bit depth, color type, CRC
        "0000000A49444154"  # IDAT length+name
        "789C6300010000050001"  # minimal zlib stream
        "0D0A2DB4"            # IDAT CRC
        "0000000049454E44"  # IEND length+name
        "AE426082"           # IEND CRC
    )
    p = tmp_path / "pixel.png"
    p.write_bytes(png_bytes)
    return p


@pytest.fixture()
def tmp_jpg(tmp_path):
    p = tmp_path / "photo.jpg"
    p.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 32 + b"\xff\xd9")
    return p


@pytest.fixture()
def tmp_unknown(tmp_path):
    p = tmp_path / "scan.bmp"
    p.write_bytes(b"BM" + b"\x00" * 32)
    return p


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestImageFallbackOpenAICompatible:
    """
    Garante que imagens são corretamente serializadas como data URL
    no branch OpenAI-compatible (provider != google/gemini).
    """

    def test_image_path_makes_user_content_a_list_with_image_url(
        self, tmp_png, monkeypatch
    ):
        """messages[1].content deve virar lista com text + image_url (data URL PNG)."""
        captured = {}

        class _FakeResponse:
            status_code = 200
            ok = True

            def json(self):
                return {
                    "choices": [
                        {"message": {"content": '{"title": "ok"}'}}
                    ]
                }

        def _fake_post(url, json=None, headers=None, timeout=None):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return _FakeResponse()

        monkeypatch.setattr(llm_client.requests, "post", _fake_post)

        # Configurar credenciais via get_credentials
        monkeypatch.setattr(
            llm_client, "get_credentials",
            lambda provider: {"key": "sk-fake", "url": "https://api.openai.com/v1",
                              "type": "api_key"},
        )

        result = llm_client.call_llm_structured(
            prompt="describe this image",
            system_prompt="be concise",
            response_model=_SampleModel,
            image_path=str(tmp_png),
            provider="openai",
            model="gpt-4o",
        )

        # Validação: o resultado Pydantic é o do mock
        assert result.title == "ok"

        # Validação principal do PATCH 1
        payload = captured["json"]
        assert payload is not None
        user_msg = payload["messages"][1]
        content = user_msg["content"]
        assert isinstance(content, list), (
            f"image_path deve transformar messages[1].content em list, "
            f"obtido {type(content).__name__}: {content!r}"
        )
        assert content[0]["type"] == "text"
        assert content[0]["text"] == "describe this image"
        assert content[1]["type"] == "image_url"
        url = content[1]["image_url"]["url"]
        assert url.startswith("data:image/png;base64,"), (
            f"Data URL esperado 'data:image/png;base64,...', obtido: {url[:60]}..."
        )
        # O base64 deve decodificar para os bytes do PNG
        b64_part = url.split(",", 1)[1]
        assert base64.b64decode(b64_part) == tmp_png.read_bytes()

    def test_image_path_jpg_uses_jpeg_mime(self, tmp_jpg, monkeypatch):
        """Extensão .jpg → MIME image/jpeg (não image/png)."""
        captured = {}

        class _FakeResponse:
            status_code = 200
            ok = True
            def json(self):
                return {"choices": [{"message": {"content": '{"title": "ok"}'}}]}

        def _fake_post(url, json=None, headers=None, timeout=None):
            captured["json"] = json
            return _FakeResponse()

        monkeypatch.setattr(llm_client.requests, "post", _fake_post)
        monkeypatch.setattr(
            llm_client, "get_credentials",
            lambda provider: {"key": "sk", "url": "https://api.openai.com/v1",
                              "type": "api_key"},
        )

        llm_client.call_llm_structured(
            prompt="look", system_prompt="sys", response_model=_SampleModel,
            image_path=str(tmp_jpg), provider="openai", model="gpt-4o",
        )

        url = captured["json"]["messages"][1]["content"][1]["image_url"]["url"]
        assert url.startswith("data:image/jpeg;base64,"), (
            f".jpg deve virar image/jpeg, obtido: {url[:40]}..."
        )

    def test_image_path_unknown_extension_defaults_to_png(self, tmp_unknown, monkeypatch):
        """Extensão desconhecida (.bmp) → fallback para image/png (paridade com Google)."""
        captured = {}

        class _FakeResponse:
            status_code = 200
            ok = True
            def json(self):
                return {"choices": [{"message": {"content": '{"title": "ok"}'}}]}

        def _fake_post(url, json=None, headers=None, timeout=None):
            captured["json"] = json
            return _FakeResponse()

        monkeypatch.setattr(llm_client.requests, "post", _fake_post)
        monkeypatch.setattr(
            llm_client, "get_credentials",
            lambda provider: {"key": "sk", "url": "https://api.openai.com/v1",
                              "type": "api_key"},
        )

        llm_client.call_llm_structured(
            prompt="x", system_prompt="y", response_model=_SampleModel,
            image_path=str(tmp_unknown), provider="openai", model="gpt-4o",
        )

        url = captured["json"]["messages"][1]["content"][1]["image_url"]["url"]
        assert url.startswith("data:image/png;base64,"), (
            f"Extensão desconhecida deveria usar image/png (paridade com Google); "
            f"obtido: {url[:40]}..."
        )

    def test_no_image_path_keeps_user_content_as_string(self, monkeypatch):
        """Sem image_path, messages[1].content continua sendo string (regressão)."""
        captured = {}

        class _FakeResponse:
            status_code = 200
            ok = True
            def json(self):
                return {"choices": [{"message": {"content": '{"title": "ok"}'}}]}

        def _fake_post(url, json=None, headers=None, timeout=None):
            captured["json"] = json
            return _FakeResponse()

        monkeypatch.setattr(llm_client.requests, "post", _fake_post)
        monkeypatch.setattr(
            llm_client, "get_credentials",
            lambda provider: {"key": "sk", "url": "https://api.openai.com/v1",
                              "type": "api_key"},
        )

        llm_client.call_llm_structured(
            prompt="hello", system_prompt="sys", response_model=_SampleModel,
            provider="openai", model="gpt-4o",
        )

        user_content = captured["json"]["messages"][1]["content"]
        assert isinstance(user_content, str), (
            f"Sem image_path o content deve continuar string, "
            f"obtido {type(user_content).__name__}"
        )
        assert user_content == "hello"
