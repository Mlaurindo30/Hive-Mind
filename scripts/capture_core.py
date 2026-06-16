#!/usr/bin/env python3
"""
capture_core.py — Infraestrutura ÚNICA de transporte do pipeline de captura.

Contém SÓ o que é genérico e não pertence a nenhuma ferramenta específica:
  • conexão com o worker do claude-mem (_post / worker_alive)
  • idempotência por CONTENT-HASH (content_hash / _norm)
  • motor de ingestão (ingest) — emite init/observation/summarize sem duplicar
  • estado ISOLADO por plataforma (load_state/save_state → capture-state/<tool>.json)
  • utilitários de mtime (WAL-aware) e coerção de texto

NÃO contém lógica de parsing de NENHUMA ferramenta — cada uma tem seu próprio
módulo em parsers/<tool>.py. Aqui é a única camada compartilhada (transporte).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.request
from pathlib import Path

HOME = Path.home()
BASE = f"http://{os.environ.get('CLAUDE_MEM_WORKER_HOST','127.0.0.1')}:{os.environ.get('CLAUDE_MEM_WORKER_PORT','37700')}"
DATA_DIR = Path(os.environ.get("CLAUDE_MEM_DATA_DIR", str(HOME / ".claude-mem")))
PROJECT = os.environ.get("CAPTURE_BRIDGE_PROJECT", "Hive-Mind")
# Máx. de observações por sessão por execução. 0 = SEM limite (comportamento do
# realtime antigo). A idempotência por content-hash + a janela de recência já
# evitam flood, então o default é ilimitado; defina >0 só se quiser teto.
OBS_CAP = int(os.environ.get("CAPTURE_TAILER_OBS_CAP", "0"))
# Corte de recência por-sessão (epoch ms) p/ DBs SQLite multi-sessão. Os callers
# (tailer/daemon) ajustam isto; os parsers SQLite leem core.SESSION_CUTOFF_MS.
SESSION_CUTOFF_MS = 0

# Estado ISOLADO por plataforma (1 arquivo por ferramenta). STATE = legado global
# (só p/ migração one-shot).
STATE = DATA_DIR / "tailer-state.json"
STATE_DIR = DATA_DIR / "capture-state"


# ── util de texto (genérico, não-tool-específico) ──────────────────────────────
def _text(c) -> str:
    """Coerção de conteúdo (str | lista de blocos {text} | outro) → str."""
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        t = " ".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("text"))
        return t or json.dumps(c, ensure_ascii=False)[:2000]
    return str(c or "")


def _norm(s: str) -> str:
    """Normaliza texto p/ identidade estável de conteúdo (whitespace + caixa)."""
    return re.sub(r"\s+", " ", (s or "").strip()).lower()


def content_hash(*parts: str) -> str:
    """Identidade ESTÁVEL de um prompt/observação: independe de offset, índice ou
    ordem de reescrita do arquivo. Mesma mensagem → mesmo hash → emitida 1× só,
    não importa quantas vezes a fonte seja re-parseada ou por quantos processos.
    Vira também o tool_use_id, então o worker deduplica entre processos."""
    return hashlib.sha1("|".join(parts).encode("utf-8", errors="ignore")).hexdigest()


# ── mtime WAL-aware ────────────────────────────────────────────────────────────
def _src_mtime(p: Path) -> float:
    """mtime efetivo de uma fonte. SQLite em modo WAL grava no sidecar -wal (o .db
    só muda no checkpoint), então o mtime do .db fica horas atrasado. Considera o
    maior mtime entre o arquivo e os sidecars -wal/-shm."""
    mt = 0.0
    for cand in (p, Path(str(p) + "-wal"), Path(str(p) + "-shm")):
        try:
            mt = max(mt, cand.stat().st_mtime)
        except OSError:
            pass
    return mt


# ── conexão com o worker ───────────────────────────────────────────────────────
def _post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"{BASE}{path}", data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode() or "{}")
    except Exception as e:
        msg = ""
        if hasattr(e, "read"):
            try:
                msg = e.read().decode()[:200]
            except Exception:
                pass
        print(f"  ⚠ {path}: {e} {msg}")
        return {"error": str(e)}


def worker_alive() -> bool:
    try:
        with urllib.request.urlopen(f"{BASE}/api/health", timeout=5) as r:
            return r.status == 200
    except Exception:
        return False


# ── estado isolado por plataforma ──────────────────────────────────────────────
def _migrate_legacy_state() -> None:
    """Migra o tailer-state.json global (legado) para capture-state/<plataforma>.json
    uma única vez. Não destrói o legado."""
    if not STATE.exists() or (STATE_DIR / ".migrated").exists():
        return
    try:
        legacy = json.loads(STATE.read_text())
    except Exception:
        return
    buckets: dict[str, dict] = {}
    for skey, val in legacy.items():
        plat = skey.split(":", 2)[1] if skey.startswith("rt:") else (
            skey.split(":", 1)[0] if ":" in skey else skey)
        buckets.setdefault(plat, {})[skey] = val
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    for plat, data in buckets.items():
        save_state(plat, data)
    (STATE_DIR / ".migrated").write_text(time.strftime("%Y-%m-%dT%H:%M:%S"))


def load_state(platform: str) -> dict:
    """Estado isolado da plataforma. Cada ferramenta tem o seu arquivo."""
    _migrate_legacy_state()
    p = STATE_DIR / f"{platform}.json"
    try:
        return json.loads(p.read_text()) if p.exists() else {}
    except Exception:
        return {}


def save_state(platform: str, s: dict) -> None:
    """Escrita ATÔMICA (tmp + rename) do arquivo por-plataforma."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    p = STATE_DIR / f"{platform}.json"
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(s, indent=2))
    tmp.replace(p)


# ── motor de ingestão (idempotente por content-hash) ───────────────────────────
def ingest(platform: str, sess: dict, state: dict) -> int:
    """Emite prompt/observação/sumário ao worker, deduplicando por content-hash.
    `sess` = {sid, prompt, turns:[{tool_name, tool_input:{prompt?}, tool_response}], last}.
    `state` = estado ISOLADO da plataforma. Re-chamar com a mesma sessão N vezes
    (reparse / reescrita / 2 processos) → só conteúdo NOVO emite. `seen` (set de
    hashes) é o único estado por sessão."""
    sid = sess.get("sid")
    prompt, turns, last_text = sess.get("prompt"), sess.get("turns") or [], sess.get("last")
    if not sid or (not prompt and not turns):
        return 0
    skey = f"{platform}:{sid}"
    rec = state.setdefault(skey, {"inited": False, "seen": []})
    seen = set(rec.get("seen") or [])

    def emit_prompt(text: str) -> bool:
        norm = _norm(text)
        if not norm:
            return False
        h = content_hash(sid, "p", norm)
        if h in seen:
            return False
        _post("/api/sessions/init", {
            "contentSessionId": sid, "project": PROJECT, "platformSource": platform,
            "prompt": text, "customTitle": f"[{platform}] {text[:60]}",
        })
        seen.add(h)
        return True

    if not rec["inited"]:
        _post("/api/sessions/init", {
            "contentSessionId": sid, "project": PROJECT, "platformSource": platform,
            "prompt": prompt or "(sessão)", "customTitle": f"[{platform}] {(prompt or '')[:60]}",
        })
        rec["inited"] = True
        if prompt:
            seen.add(content_hash(sid, "p", _norm(prompt)))

    sent = 0
    for t in turns:
        if OBS_CAP and sent >= OBS_CAP:   # OBS_CAP=0 → sem limite
            print(f"  ⏳ {platform}:{sid[:12]}: cap {OBS_CAP} atingido; resto depois")
            break
        if isinstance(t.get("tool_input"), dict):
            tp = str(t["tool_input"].get("prompt") or "").strip()
            if tp:
                emit_prompt(tp)
        tn = (t.get("tool_name") or "Tool").strip() or "Tool"
        resp = str(t.get("tool_response") or "")
        ho = content_hash(sid, "o", tn, _norm(resp))
        if ho in seen:
            continue
        obs_res = _post("/api/sessions/observations", {
            "contentSessionId": sid, "tool_name": tn,
            "tool_input": t.get("tool_input") or {}, "tool_response": {"result": resp},
            "platformSource": platform, "cwd": str(Path.cwd()),
            "tool_use_id": f"{platform}:{sid}:{ho[:20]}",
        })
        if obs_res.get("error") or obs_res.get("stored") is False:
            continue
        seen.add(ho)
        sent += 1

    rec["seen"] = list(seen)

    if sent:
        _post("/api/sessions/summarize", {
            "contentSessionId": sid, "platformSource": platform,
            "last_assistant_message": last_text or prompt or "sessão concluída",
        })
        print(f"  ✓ {platform}:{sid[:12]} → {sent} nova(s)")
    return sent
