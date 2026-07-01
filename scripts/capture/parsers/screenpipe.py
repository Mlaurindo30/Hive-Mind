"""Parser Screenpipe — consome OCR e áudio via REST API em localhost:3030.

Screenpipe é um daemon Rust que captura tela continuamente, processa com OCR
(Tesseract/Apple Vision) e transcreve áudio com Whisper, tudo local.

API:
  GET /health                       → {"status": "healthy"|"ok", ...}
  GET /search?content_type=ocr&...  → OCR frames
  GET /search?content_type=audio&.. → transcrições Whisper
  POST /screenshot                  → captura on-demand (retorna path)

Configuração:
  SCREENPIPE_BASE    (env, default: http://localhost:3030)
  SCREENPIPE_API_KEY (env, optional — Bearer token for auth-enabled instances)
"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone

SCREENPIPE_BASE = os.environ.get("SCREENPIPE_BASE", "http://localhost:3030")
_TIMEOUT = int(os.environ.get("SCREENPIPE_TIMEOUT", "5"))
_API_KEY = os.environ.get("SCREENPIPE_API_KEY", "")

_HEALTHY = {"ok", "healthy"}


def _api(path: str, params: dict | None = None) -> dict:
    """GET request à API do Screenpipe. Retorna {} em qualquer erro."""
    url = f"{SCREENPIPE_BASE}{path}"
    if params:
        qs = "&".join(f"{k}={urllib.request.quote(str(v))}" for k, v in params.items())
        url = f"{url}?{qs}"
    try:
        headers = {}
        if _API_KEY:
            headers["Authorization"] = f"Bearer {_API_KEY}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            return json.loads(r.read().decode())
    except Exception:
        return {}


def screenpipe_alive() -> bool:
    """Retorna True se Screenpipe estiver rodando e saudável."""
    return _api("/health").get("status") in _HEALTHY


def fetch_recent_ocr(since_minutes: int = 60, limit: int = 50) -> list[dict]:
    """Retorna sessões de OCR recentes formatadas para o pipeline de captura.

    Cada item é um dict compatível com capture_core.ingest():
      sid, prompt, turns=[{tool_name, tool_input, tool_response}], last
    """
    start = (datetime.now(timezone.utc) - timedelta(minutes=since_minutes)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    data = _api("/search", {"content_type": "ocr", "start_time": start, "limit": limit})
    sessions = []
    for item in data.get("data", []):
        content = item.get("content", {})
        text = content.get("text", "").strip()
        if not text:
            continue
        frame_id = str(item.get("content_id", item.get("id", "")))
        app = content.get("app_name", "unknown")
        sessions.append({
            "sid": f"screenpipe:{frame_id}",
            "prompt": f"[{app}] {text[:120]}",
            "turns": [{
                "tool_name": "ScreenCapture",
                "tool_input": {"app": app, "text": text[:500]},
                "tool_response": text,
            }],
            "last": text[:200],
        })
    return sessions


def fetch_recent_audio(since_minutes: int = 60, limit: int = 20) -> list[dict]:
    """Retorna transcrições Whisper recentes formatadas para o pipeline."""
    start = (datetime.now(timezone.utc) - timedelta(minutes=since_minutes)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    data = _api("/search", {"content_type": "audio", "start_time": start, "limit": limit})
    sessions = []
    for item in data.get("data", []):
        content = item.get("content", {})
        text = content.get("transcription", "").strip()
        if not text:
            continue
        chunk_id = str(item.get("content_id", item.get("id", "")))
        sessions.append({
            "sid": f"screenpipe:audio:{chunk_id}",
            "prompt": f"[áudio] {text[:120]}",
            "turns": [{
                "tool_name": "AudioTranscription",
                "tool_input": {"transcription": text[:500]},
                "tool_response": text,
            }],
            "last": text[:200],
        })
    return sessions


def capture_screenshot(description: str = "", monitor: int | None = None) -> dict:
    """Solicita captura de tela on-demand ao Screenpipe.

    Retorna {"path": str, "source": "screenpipe"} ou {"error": str}.
    """
    body = {"description": description}
    if monitor is not None:
        body["monitor"] = monitor
    payload = json.dumps(body).encode()
    headers = {"Content-Type": "application/json"}
    if _API_KEY:
        headers["Authorization"] = f"Bearer {_API_KEY}"
    req = urllib.request.Request(
        f"{SCREENPIPE_BASE}/screenshot",
        data=payload,
        method="POST",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            data = json.loads(r.read().decode())
        path = data.get("path", "")
        if path:
            return {"path": path, "description": description, "source": "screenpipe"}
        return {"error": "Screenpipe retornou path vazio"}
    except Exception as e:
        return {"error": str(e)}
