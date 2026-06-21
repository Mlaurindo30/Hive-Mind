"""Testes do parser Screenpipe (P1).

Verifica:
  1. screenpipe_alive() retorna False quando Screenpipe não responde
  2. fetch_recent_ocr() retorna [] quando Screenpipe está offline
  3. fetch_recent_audio() retorna [] quando Screenpipe está offline
  4. Formato das sessões retornadas (campos obrigatórios)
  5. _parse_screenpipe() adapter retorna [] sem Screenpipe
  6. _capture_screen() cai no fallback quando Screenpipe offline
  7. Testes live (skip se Screenpipe não estiver rodando)
"""
import sys
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "capture"))
sys.path.insert(0, str(ROOT / "scripts"))

from scripts.capture.parsers import screenpipe as sp


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_alive() -> bool:
    return sp.screenpipe_alive()


def _make_ocr_item(frame_id="1", app="Code", text="hello world"):
    return {
        "content_id": frame_id,
        "content": {"text": text, "app_name": app},
    }


def _make_audio_item(chunk_id="99", transcription="oi tudo bem"):
    return {
        "content_id": chunk_id,
        "content": {"transcription": transcription},
    }


# ---------------------------------------------------------------------------
# Testes offline (sempre rodam)
# ---------------------------------------------------------------------------

def test_screenpipe_alive_offline(monkeypatch):
    """screenpipe_alive() → False quando API não responde."""
    monkeypatch.setattr(sp, "_api", lambda *_a, **_kw: {})
    assert sp.screenpipe_alive() is False


def test_fetch_recent_ocr_offline(monkeypatch):
    """fetch_recent_ocr() → [] quando Screenpipe está offline."""
    monkeypatch.setattr(sp, "_api", lambda *_a, **_kw: {})
    assert sp.fetch_recent_ocr() == []


def test_fetch_recent_audio_offline(monkeypatch):
    """fetch_recent_audio() → [] quando Screenpipe está offline."""
    monkeypatch.setattr(sp, "_api", lambda *_a, **_kw: {})
    assert sp.fetch_recent_audio() == []


def test_fetch_recent_ocr_formato(monkeypatch):
    """fetch_recent_ocr() retorna sessões com campos obrigatórios."""
    fake_data = {"data": [_make_ocr_item("42", "Terminal", "ls -la /tmp")]}
    monkeypatch.setattr(sp, "_api", lambda *_a, **_kw: fake_data)

    sessions = sp.fetch_recent_ocr()
    assert len(sessions) == 1
    s = sessions[0]
    assert s["sid"] == "screenpipe:42"
    assert "Terminal" in s["prompt"]
    assert s["turns"][0]["tool_name"] == "ScreenCapture"
    assert "ls -la" in s["turns"][0]["tool_response"]
    assert s["last"]


def test_fetch_recent_audio_formato(monkeypatch):
    """fetch_recent_audio() retorna sessões com campos obrigatórios."""
    fake_data = {"data": [_make_audio_item("7", "reunião de sprint agora")]}
    monkeypatch.setattr(sp, "_api", lambda *_a, **_kw: fake_data)

    sessions = sp.fetch_recent_audio()
    assert len(sessions) == 1
    s = sessions[0]
    assert s["sid"] == "screenpipe:audio:7"
    assert s["turns"][0]["tool_name"] == "AudioTranscription"
    assert "reunião" in s["turns"][0]["tool_response"]


def test_fetch_ocr_ignora_texto_vazio(monkeypatch):
    """fetch_recent_ocr() descarta itens com texto vazio."""
    fake_data = {"data": [
        _make_ocr_item("1", "App", ""),
        _make_ocr_item("2", "App", "   "),
        _make_ocr_item("3", "App", "texto válido"),
    ]}
    monkeypatch.setattr(sp, "_api", lambda *_a, **_kw: fake_data)
    sessions = sp.fetch_recent_ocr()
    assert len(sessions) == 1
    assert "válido" in sessions[0]["turns"][0]["tool_response"]


def test_parse_screenpipe_adapter_offline():
    """_parse_screenpipe() retorna [] quando Screenpipe está offline."""
    from scripts.capture.capture_adapters import _parse_screenpipe
    with patch("parsers.screenpipe.screenpipe_alive", return_value=False):
        result = _parse_screenpipe()
    assert result == []


def test_parse_screenpipe_adapter_nao_quebra_sem_modulo():
    """_parse_screenpipe() retorna [] mesmo se o módulo não for importável."""
    from scripts.capture.capture_adapters import _parse_screenpipe
    with patch.dict(sys.modules, {"parsers.screenpipe": None}):
        result = _parse_screenpipe()
    assert result == []


def test_capture_screenshot_offline(monkeypatch):
    """capture_screenshot() retorna {"error": ...} quando Screenpipe offline."""
    monkeypatch.setattr(sp, "SCREENPIPE_BASE", "http://localhost:9")
    result = sp.capture_screenshot("teste")
    assert "error" in result
    assert result.get("path") is None


def test_capture_screenshot_sem_path(monkeypatch):
    """capture_screenshot() retorna {"error": ...} quando path está vazio."""
    monkeypatch.setattr(sp, "_api", lambda *_a, **_kw: {})

    import urllib.request as _ur

    class _FakeResp:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self): return b'{"path": ""}'

    monkeypatch.setattr(_ur, "urlopen", lambda *_a, **_kw: _FakeResp())
    result = sp.capture_screenshot("desc")
    assert "error" in result


# ---------------------------------------------------------------------------
# Testes live (skip se Screenpipe não rodando)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _is_alive(), reason="Screenpipe não está rodando em localhost:3030")
def test_live_screenpipe_alive():
    assert sp.screenpipe_alive() is True


@pytest.mark.skipif(not _is_alive(), reason="Screenpipe não está rodando em localhost:3030")
def test_live_fetch_ocr_retorna_lista():
    sessions = sp.fetch_recent_ocr(since_minutes=5, limit=5)
    assert isinstance(sessions, list)
    for s in sessions:
        assert "sid" in s and s["sid"].startswith("screenpipe:")
        assert "turns" in s and s["turns"]


@pytest.mark.skipif(not _is_alive(), reason="Screenpipe não está rodando em localhost:3030")
def test_live_fetch_audio_retorna_lista():
    sessions = sp.fetch_recent_audio(since_minutes=30, limit=5)
    assert isinstance(sessions, list)
