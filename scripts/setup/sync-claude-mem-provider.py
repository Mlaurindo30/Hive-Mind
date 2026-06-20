#!/usr/bin/env python3
"""
sync-claude-mem-provider.py — Ponte: escolha do papel `claude_mem` (setup-brain)
→ configuração real do claude-mem project-local.

O setup-brain.py grava no .env do projeto:
    HIVE_CLAUDE_MEM_PROVIDER / HIVE_CLAUDE_MEM_MODEL  (+ a credencial do provider)

O claude-mem (worker) só entende 3 slots:
    - claude     (Anthropic SDK)        ← provider anthropic/claude
    - gemini     (Gemini SDK)           ← provider google/gemini
    - "openrouter" = cliente OpenAI-compatible com BASE_URL configurável
                                        ← QUALQUER outro provider OpenAI-compat
                                          (openai, deepseek, qwen, nvidia,
                                           ollama, lmstudio, openrouter…)

Este script faz o mapeamento e escreve em settings.json, preservando as demais
chaves, e reinicia o worker. É chamado pelo setup-brain (ao escolher o papel
claude_mem) e pelo install.sh (instalação limpa).

Uso:
    python scripts/sync-claude-mem-provider.py            # aplica e reinicia worker
    python scripts/sync-claude-mem-provider.py --no-restart
    python scripts/sync-claude-mem-provider.py --print    # só mostra o que aplicaria
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

from core.auth import PROVIDERS_CONFIG, load_env  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
CMEM_DATA_DIR = ROOT / "claude-mem" / "data"
CMEM_SETTINGS = Path(os.environ.get("CLAUDE_MEM_DATA_DIR", str(CMEM_DATA_DIR))) / "settings.json"
GLOBAL_CMEM_SETTINGS = Path.home() / ".claude-mem" / "settings.json"

# provider do Hive (core/auth) → slot nativo do claude-mem
GEMINI_PROVIDERS = {"google", "gemini"}
CLAUDE_PROVIDERS = {"anthropic", "claude"}


def _key_for(provider: str, env: dict) -> str:
    """Resolve a credencial do provider a partir do .env (api key ou token OAuth)."""
    cfg = PROVIDERS_CONFIG.get(provider, {})
    return (
        env.get(cfg.get("env_var", ""), "")
        or env.get(cfg.get("alt_env_var", ""), "")
        or env.get(f"{provider.upper()}_ACCESS_TOKEN", "")
        or "local"  # providers locais (ollama/lmstudio) não exigem chave
    )


def local_runtime_updates() -> dict[str, str]:
    """Campos que nunca podem apontar para ~/.claude-mem no runtime do Hive-Mind."""
    data_dir = ROOT / "claude-mem" / "data"
    return {
        "CLAUDE_MEM_DATA_DIR": str(data_dir),
        "CLAUDE_MEM_WORKER_HOST": "127.0.0.1",
        "CLAUDE_MEM_WORKER_PORT": "37700",
        "CLAUDE_MEM_CHROMA_ENABLED": "false",
        "FASTEMBED_CACHE_PATH": str(data_dir / "models"),
        "CLAUDE_MEM_TRANSCRIPTS_CONFIG_PATH": str(data_dir / "transcript-watch.json"),
    }


# Chaves de path local que NÃO devem sobrescrever o seed global (worker systemd usa ~/.claude-mem).
_GLOBAL_SEED_EXCLUDE = {"CLAUDE_MEM_DATA_DIR", "FASTEMBED_CACHE_PATH", "CLAUDE_MEM_TRANSCRIPTS_CONFIG_PATH"}


# claude-mem valida CLAUDE_MEM_GEMINI_MODEL contra esta whitelist no save (UI e API).
# Gravar um valor fora dela faz QUALQUER save retornar 400 e quebra o Uif inteiro.
GEMINI_ALLOWED = {"gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-3-flash-preview"}
GEMINI_DEFAULT = "gemini-2.5-flash"


def build_updates(provider: str, model: str, env: dict) -> dict:
    """Constrói as chaves CLAUDE_MEM_* para o provider/modelo escolhido."""
    provider = (provider or "").lower()
    cfg = PROVIDERS_CONFIG.get(provider, {})
    key = _key_for(provider, env)

    if provider in GEMINI_PROVIDERS:
        gmodel = model if model in GEMINI_ALLOWED else GEMINI_DEFAULT
        if gmodel != model:
            print(f"  ⚠ '{model}' não é um modelo gemini aceito pelo claude-mem "
                  f"({', '.join(sorted(GEMINI_ALLOWED))}); usando {gmodel}.")
        return {
            **local_runtime_updates(),
            "CLAUDE_MEM_PROVIDER": "gemini",
            "CLAUDE_MEM_GEMINI_MODEL": gmodel,
            "CLAUDE_MEM_GEMINI_API_KEY": key,
        }
    if provider in CLAUDE_PROVIDERS:
        return {
            **local_runtime_updates(),
            "CLAUDE_MEM_PROVIDER": "claude",
            "CLAUDE_MEM_MODEL": model,
            "CLAUDE_MEM_CLAUDE_AUTH_METHOD": "api-key" if key and key != "local" else "subscription",
            "ANTHROPIC_API_KEY": key if key and key != "local" else "",
        }
    # qualquer outro = slot OpenAI-compatible (base_url do provider)
    return {
        **local_runtime_updates(),
        "CLAUDE_MEM_PROVIDER": "openrouter",
        "CLAUDE_MEM_OPENROUTER_BASE_URL": cfg.get("base_url", ""),
        "CLAUDE_MEM_OPENROUTER_API_KEY": key,
        "CLAUDE_MEM_OPENROUTER_MODEL": model,
    }


import datetime
import urllib.request

WORKER = f"http://{os.environ.get('CLAUDE_MEM_WORKER_HOST','127.0.0.1')}:{os.environ.get('CLAUDE_MEM_WORKER_PORT','37700')}"
WORKER_LOG_DIR = Path.home() / ".claude-mem" / "logs"


def _recent_quota_error(minutes: int = 30) -> bool:
    """True se o worker registrou erro 429 (quota esgotada) nos últimos N minutos."""
    today = datetime.date.today().isoformat()
    log_file = WORKER_LOG_DIR / f"claude-mem-{today}.log"
    if not log_file.exists():
        return False
    cutoff = datetime.datetime.now() - datetime.timedelta(minutes=minutes)
    try:
        lines = log_file.read_text(errors="replace").splitlines()
        for line in reversed(lines):
            if "[ERROR]" not in line:
                continue
            if "quota exhausted" not in line.lower() and "status 429" not in line:
                continue
            try:
                ts = datetime.datetime.strptime(line[1:24], "%Y-%m-%d %H:%M:%S.%f")
                if ts >= cutoff:
                    return True
                break
            except ValueError:
                pass
    except Exception:
        pass
    return False


def apply(updates: dict) -> None:
    """Aplica via a MESMA API que a UI do claude-mem usa (POST /api/settings →
    tabela viewer_settings). É a fonte única que a geração lê ao vivo — evita o
    split-brain com o settings.json e com mudanças feitas direto na UI :37700."""
    data = json.dumps(updates).encode()
    req = urllib.request.Request(
        f"{WORKER}/api/settings", data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
    except Exception as exc:
        # worker pode estar fora (ex.: durante o install) — o seed em settings.json
        # abaixo garante a config no próximo start.
        print(f"  ⚠ API /api/settings indisponível ({exc}); aplicando só o seed em settings.json")
    # Mantém o settings.json (seed de startup) coerente com a escolha, para um
    # restart nunca reintroduzir um provider diferente.
    try:
        CMEM_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        cfg = json.loads(CMEM_SETTINGS.read_text()) if CMEM_SETTINGS.exists() else {}
        cfg.update(updates)
        CMEM_SETTINGS.write_text(json.dumps(cfg, indent=2) + "\n")
    except Exception:
        pass  # a API (viewer_settings) é a fonte de verdade; arquivo é só seed
    # Atualiza o seed global (~/.claude-mem) para restarts do worker systemd.
    # Exclui paths project-local que não fazem sentido no contexto do worker global.
    try:
        if GLOBAL_CMEM_SETTINGS.exists():
            gcfg = json.loads(GLOBAL_CMEM_SETTINGS.read_text())
            gcfg.update({k: v for k, v in updates.items() if k not in _GLOBAL_SEED_EXCLUDE})
            GLOBAL_CMEM_SETTINGS.write_text(json.dumps(gcfg, indent=2) + "\n")
    except Exception:
        pass


def restart_worker() -> None:
    """PROVIDER/MODEL aplicam ao vivo via /api/settings, mas o BASE_URL do slot
    OpenAI-compat é lido do seed (settings.json) só no startup — então quando ele
    muda (ex.: trocar pra ollama local), o worker PRECISA reiniciar pra carregar."""
    import subprocess
    subprocess.run(("systemctl", "--user", "restart", "sinapse-claude-mem.service"),
                   check=False, text=True)


def main() -> int:
    env = load_env()
    provider = env.get("HIVE_CLAUDE_MEM_PROVIDER", "").strip()
    model = env.get("HIVE_CLAUDE_MEM_MODEL", "").strip()

    # Cascade: herda do DREAMER se o papel claude_mem não estiver configurado
    if not provider or not model:
        provider = env.get("HIVE_DREAMER_PROVIDER", "").strip()
        model = env.get("HIVE_DREAMER_MODEL", "").strip()
        if provider and model:
            print(f"  ↩ HIVE_CLAUDE_MEM_PROVIDER/MODEL ausente; herdando DREAMER ({provider}/{model})")
    if not provider or not model:
        print("⊘ Papel claude_mem não configurado "
              "(HIVE_CLAUDE_MEM/DREAMER PROVIDER/MODEL ausentes). Nada a sincronizar.")
        return 0

    # Fallback automático: detecta quota esgotada nos logs e usa HIVE_CLAUDE_MEM_FALLBACK_*
    force_fallback = "--fallback" in sys.argv
    if force_fallback or _recent_quota_error():
        fb_p = env.get("HIVE_CLAUDE_MEM_FALLBACK_PROVIDER", "").strip()
        fb_m = env.get("HIVE_CLAUDE_MEM_FALLBACK_MODEL", "").strip()
        if fb_p and fb_m and fb_p.lower() != provider.lower():
            reason = "--fallback" if force_fallback else "quota esgotada (429) recente"
            print(f"  ⚠ {reason} em '{provider}'; aplicando fallback '{fb_p}/{fb_m}'")
            provider, model = fb_p, fb_m
        elif force_fallback:
            print(f"  ⚠ --fallback solicitado mas HIVE_CLAUDE_MEM_FALLBACK_PROVIDER/MODEL não configurados.")

    updates = build_updates(provider, model, env)
    safe = {k: ("***" if "KEY" in k or "TOKEN" in k else v) for k, v in updates.items()}
    print(f"claude-mem ← {provider}/{model}")
    print(json.dumps(safe, indent=2))

    if "--print" in sys.argv:
        return 0

    apply(updates)
    print("✓ aplicado via /api/settings (live) + seeds (projeto + global ~/.claude-mem)")
    if "CLAUDE_MEM_OPENROUTER_BASE_URL" in updates:
        restart_worker()
        print("✓ worker reiniciado (base_url do slot OpenAI-compat aplicado)")

    fb_provider = env.get("HIVE_CLAUDE_MEM_FALLBACK_PROVIDER", "").strip()
    fb_model = env.get("HIVE_CLAUDE_MEM_FALLBACK_MODEL", "").strip()
    if fb_provider and fb_model:
        print(f"  ℹ Fallback disponível: {fb_provider}/{fb_model} (activa quando quota esgotar)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
