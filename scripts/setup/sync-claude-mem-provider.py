#!/usr/bin/env python3
"""
sync-claude-mem-provider.py — Ponte: escolha do papel `claude_mem` (setup-brain)
→ configuração real do claude-mem global.

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

Data dir: desde 2026-08-22 o canônico é o do projeto (ROOT/claude-mem/data —
onde o supervisor lança o worker vendorizado), com fallback para ~/.claude-mem
em instalações sem esse diretório. A env CLAUDE_MEM_DATA_DIR sempre vence.
O seed global continua sendo gravado por compatibilidade.

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

from core.auth import PROVIDERS_CONFIG, get_role_config, load_env  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
GLOBAL_CMEM_DATA_DIR = Path.home() / ".claude-mem"
GLOBAL_CMEM_SETTINGS = GLOBAL_CMEM_DATA_DIR / "settings.json"
# Data dir canônico do worker gerenciado pelo Hive-Mind (vendor integrations/claude-mem):
# o supervisor lança o worker com CLAUDE_MEM_DATA_DIR apontando para cá. Desde a
# decisão de 2026-08-22, este arquivo do projeto é a verdade; o global (~/.claude-mem)
# permanece apenas como seed de compatibilidade para instalações sem o dir do projeto.
PROJECT_CMEM_DATA_DIR = ROOT / "claude-mem" / "data"


def resolve_data_dir() -> Path:
    """Ordem de resolução: env CLAUDE_MEM_DATA_DIR > dir do projeto > global."""
    override = os.environ.get("CLAUDE_MEM_DATA_DIR", "").strip()
    if override:
        return Path(override)
    if PROJECT_CMEM_DATA_DIR.is_dir():
        return PROJECT_CMEM_DATA_DIR
    return GLOBAL_CMEM_DATA_DIR

# provider do Hive (core/auth) → slot nativo do claude-mem
GEMINI_PROVIDERS = {"google", "gemini"}
CLAUDE_PROVIDERS = {"anthropic", "claude"}


def _openai_compatible(cfg: dict) -> bool:
    """True se o provider serve um endpoint OpenAI-compatible por HTTP + chave.

    É o requisito do slot 'openrouter' do claude-mem (cliente OpenAI que faz
    POST /chat/completions com Bearer key). Providers CLI/OAuth NÃO atendem:
      - antigravity → base_url 'cli://agy' (shell-out, só o core fala isso)
      - gemini-cli / code-assist → base_url Code Assist (generateContent) + OAuth
    Mapear esses para o slot openrouter gera o erro fatal do worker
    "protocol must be http:, https: or s3:" (cli://) ou 404/envelope inválido.
    """
    base = cfg.get("base_url") or ""
    auth = cfg.get("auth_type") or []
    return base.startswith(("http://", "https://")) and any(
        a in ("api_key", "local") for a in auth
    )


def _usable_by_claude_mem(provider: str, cfg: dict) -> bool:
    """O claude-mem só consome 3 dialetos: Anthropic API key, Gemini API key, ou
    OpenAI-compatible HTTP+key. Providers CLI/OAuth (agy_cli, gemini_cli_oauth)
    são arquiteturalmente incompatíveis com o worker."""
    p = (provider or "").lower()
    auth = cfg.get("auth_type") or []
    if p in CLAUDE_PROVIDERS or p in GEMINI_PROVIDERS:
        return "api_key" in auth  # slots nativos usam SDK + API key, não OAuth
    return _openai_compatible(cfg)


def _key_for(provider: str, env: dict) -> str:
    """Resolve a credencial do provider a partir do .env (api key ou token OAuth)."""
    cfg = PROVIDERS_CONFIG.get(provider, {})
    return (
        env.get(cfg.get("env_var", ""), "")
        or env.get(cfg.get("alt_env_var", ""), "")
        or env.get(f"{provider.upper()}_ACCESS_TOKEN", "")
        or "local"  # providers locais (ollama/lmstudio) não exigem chave
    )


def runtime_updates() -> dict[str, str]:
    """Campos oficiais do runtime temporal do claude-mem (data dir resolvido)."""
    data_dir = resolve_data_dir()
    return {
        "CLAUDE_MEM_DATA_DIR": str(data_dir),
        "CLAUDE_MEM_WORKER_HOST": "127.0.0.1",
        "CLAUDE_MEM_WORKER_PORT": "37700",
        "CLAUDE_MEM_CHROMA_ENABLED": "false",
        "FASTEMBED_CACHE_PATH": str(data_dir / "models"),
        "CLAUDE_MEM_TRANSCRIPTS_CONFIG_PATH": str(data_dir / "transcript-watch.json"),
    }


def local_runtime_updates() -> dict[str, str]:
    """Compatibilidade: resolução dinâmica (projeto > global)."""
    return runtime_updates()


# claude-mem valida CLAUDE_MEM_GEMINI_MODEL contra esta whitelist no save (UI e API).
# Gravar um valor fora dela faz QUALQUER save retornar 400 e quebra o Uif inteiro.
GEMINI_ALLOWED = {"gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-3-flash-preview"}
GEMINI_DEFAULT = "gemini-2.5-flash"


def build_provider_chain(env: dict) -> list[dict]:
    """Materializa primary/fallback/fallback2 em entradas consumíveis pelo worker."""
    merged_env = dict(env)
    env_file = ROOT / ".env"
    if env_file.exists():
        for raw in env_file.read_text(encoding="utf-8").splitlines():
            if not raw or raw.lstrip().startswith("#") or "=" not in raw:
                continue
            key, value = raw.split("=", 1)
            merged_env[key.strip()] = value.strip().strip('"').strip("'")
    config = {
        "provider": merged_env.get("HIVE_CLAUDE_MEM_PROVIDER") or merged_env.get("HIVE_DREAMER_PROVIDER"),
        "model": merged_env.get("HIVE_CLAUDE_MEM_MODEL") or merged_env.get("HIVE_DREAMER_MODEL"),
        "fallback_provider": merged_env.get("HIVE_CLAUDE_MEM_FALLBACK_PROVIDER"),
        "fallback_model": merged_env.get("HIVE_CLAUDE_MEM_FALLBACK_MODEL"),
        "fallback2_provider": merged_env.get("HIVE_CLAUDE_MEM_FALLBACK2_PROVIDER"),
        "fallback2_model": merged_env.get("HIVE_CLAUDE_MEM_FALLBACK2_MODEL"),
    }
    if not config["fallback_provider"] and not config["provider"]:
        config = get_role_config("claude_mem")
    levels = [
        (config.get("provider"), config.get("model")),
        (config.get("fallback_provider"), config.get("fallback_model")),
        (config.get("fallback2_provider"), config.get("fallback2_model")),
    ]
    chain: list[dict] = []
    for provider, model in levels:
        provider = (provider or "").strip().lower()
        model = (model or "").strip()
        cfg = PROVIDERS_CONFIG.get(provider, {})
        if not provider or not model or not _usable_by_claude_mem(provider, cfg):
            continue
        key = _key_for(provider, merged_env)
        if provider in GEMINI_PROVIDERS:
            entry = {"slot": "gemini", "provider": provider, "model": model, "apiKey": key}
        elif provider in CLAUDE_PROVIDERS:
            entry = {
                "slot": "claude", "provider": provider, "model": model,
                "apiKey": "" if key == "local" else key,
                "authMethod": "api-key" if key and key != "local" else "subscription",
            }
        else:
            entry = {
                "slot": "openrouter", "provider": provider, "model": model,
                "baseUrl": cfg.get("base_url", ""), "apiKey": key,
            }
        if not any(existing["slot"] == entry["slot"] and existing["model"] == model
                   and existing.get("baseUrl") == entry.get("baseUrl") for existing in chain):
            chain.append(entry)
    return chain


def build_updates(provider: str, model: str, env: dict) -> dict:
    """Constrói as chaves CLAUDE_MEM_* para o provider/modelo escolhido."""
    provider = (provider or "").lower()
    cfg = PROVIDERS_CONFIG.get(provider, {})
    key = _key_for(provider, env)

    if provider in GEMINI_PROVIDERS:
        gmodel = model if model in GEMINI_ALLOWED else GEMINI_DEFAULT
        if gmodel != model:
            print(f"  ! '{model}' não é um modelo gemini aceito pelo claude-mem "
                  f"({', '.join(sorted(GEMINI_ALLOWED))}); usando {gmodel}.")
        return {
            **runtime_updates(),
            "CLAUDE_MEM_PROVIDER": "gemini",
            "CLAUDE_MEM_GEMINI_MODEL": gmodel,
            "CLAUDE_MEM_GEMINI_API_KEY": key,
        }
    if provider in CLAUDE_PROVIDERS:
        return {
            **runtime_updates(),
            "CLAUDE_MEM_PROVIDER": "claude",
            "CLAUDE_MEM_MODEL": model,
            "CLAUDE_MEM_CLAUDE_AUTH_METHOD": "api-key" if key and key != "local" else "subscription",
            "ANTHROPIC_API_KEY": key if key and key != "local" else "",
        }
    # qualquer outro = slot OpenAI-compatible (base_url do provider)
    base_url = cfg.get("base_url", "")
    if not base_url.startswith(("http://", "https://")):
        # Defesa: o worker é um cliente HTTP; um base_url 'cli://' (antigravity) ou
        # vazio causa "protocol must be http:, https: or s3:" e zera a geração.
        raise ValueError(
            f"provider '{provider}' não é OpenAI-compatible para o claude-mem "
            f"(base_url={base_url!r}). Use um provider HTTP+chave (nvidia, ollama, "
            f"openrouter, deepseek…) ou os slots nativos gemini/claude."
        )
    return {
        **runtime_updates(),
        "CLAUDE_MEM_PROVIDER": "openrouter",
        "CLAUDE_MEM_OPENROUTER_BASE_URL": base_url,
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


def _recent_auth_error(minutes: int = 30) -> bool:
    """True when the current provider was rejected with HTTP 401 or 403."""
    today = datetime.date.today().isoformat()
    log_file = WORKER_LOG_DIR / f"claude-mem-{today}.log"
    if not log_file.exists():
        return False
    cutoff = datetime.datetime.now() - datetime.timedelta(minutes=minutes)
    try:
        for line in reversed(log_file.read_text(errors="replace").splitlines()):
            if "auth error" not in line.lower() or not ("status 401" in line or "status 403" in line):
                continue
            try:
                timestamp = datetime.datetime.strptime(line[1:24], "%Y-%m-%d %H:%M:%S.%f")
            except ValueError:
                continue
            return timestamp >= cutoff
    except OSError:
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
            print(f"  ! API /api/settings indisponível ({exc}); aplicando só o seed em settings.json")
    # Mantém o seed do data dir resolvido (projeto > global) coerente com a
    # escolha, para um restart nunca reintroduzir um provider diferente.
    try:
        settings_path = resolve_data_dir() / "settings.json"
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        cfg = json.loads(settings_path.read_text()) if settings_path.exists() else {}
        cfg.update(updates)
        settings_path.write_text(json.dumps(cfg, indent=2) + "\n")
    except Exception:
        pass  # a API (viewer_settings) é a fonte de verdade; arquivo é só seed
    # Atualiza o seed global (~/.claude-mem) para restarts do worker systemd.
    try:
        GLOBAL_CMEM_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        gcfg = json.loads(GLOBAL_CMEM_SETTINGS.read_text()) if GLOBAL_CMEM_SETTINGS.exists() else {}
        gcfg.update(updates)
        GLOBAL_CMEM_SETTINGS.write_text(json.dumps(gcfg, indent=2) + "\n")
    except Exception:
        pass


def restart_worker() -> None:
    """PROVIDER/MODEL aplicam ao vivo via /api/settings, mas o BASE_URL do slot
    OpenAI-compat é lido do seed (settings.json) só no startup — então quando ele
    muda (ex.: trocar pra ollama local), o worker PRECISA reiniciar pra carregar."""
    if os.name == "nt":
        subprocess.run(
            ("node", str(ROOT / "npm" / "bin" / "hive-mind.js"), "services", "restart"),
            check=False,
            text=True,
        )
        return
    subprocess.run(("systemctl", "--user", "restart", "sinapse-claude-mem.service"), check=False, text=True)


def main() -> int:
    env = load_env()
    provider = env.get("HIVE_CLAUDE_MEM_PROVIDER", "").strip()
    model = env.get("HIVE_CLAUDE_MEM_MODEL", "").strip()

    # Cascade: herda do DREAMER se o papel claude_mem não estiver configurado
    if not provider or not model:
        provider = env.get("HIVE_DREAMER_PROVIDER", "").strip()
        model = env.get("HIVE_DREAMER_MODEL", "").strip()
        if provider and model:
            print(f"  -> HIVE_CLAUDE_MEM_PROVIDER/MODEL ausente; herdando DREAMER ({provider}/{model})")
    if not provider or not model:
        print("- Papel claude_mem não configurado "
              "(HIVE_CLAUDE_MEM/DREAMER PROVIDER/MODEL ausentes). Nada a sincronizar.")
        return 0

    # Fallback automático: quota ou credencial/endpoint rejeitado usam o modelo local.
    force_fallback = "--fallback" in sys.argv
    quota_error = _recent_quota_error()
    auth_error = _recent_auth_error()
    if force_fallback or quota_error or auth_error:
        fb_p = env.get("HIVE_CLAUDE_MEM_FALLBACK_PROVIDER", "").strip()
        fb_m = env.get("HIVE_CLAUDE_MEM_FALLBACK_MODEL", "").strip()
        if fb_p and fb_m and fb_p.lower() != provider.lower():
            reason = (
                "--fallback" if force_fallback else
                "quota esgotada (429) recente" if quota_error else
                "autenticação/endpoint rejeitado (401/403) recente"
            )
            print(f"  ! {reason} em '{provider}'; aplicando fallback '{fb_p}/{fb_m}'")
            provider, model = fb_p, fb_m
        elif force_fallback:
            print(f"  ! --fallback solicitado mas HIVE_CLAUDE_MEM_FALLBACK_PROVIDER/MODEL não configurados.")

    # Guard de compatibilidade: se o provider escolhido (ou o fallback de quota)
    # for CLI/OAuth (antigravity, gemini-cli, code-assist), o worker não consegue
    # usá-lo. Tenta o fallback configurado; se também for incompatível, aborta SEM
    # sobrescrever a config viva (não troca um setup que funciona por um quebrado).
    if not _usable_by_claude_mem(provider, PROVIDERS_CONFIG.get(provider, {})):
        print(f"  ! provider '{provider}' é CLI/OAuth — incompatível com o worker "
              f"do claude-mem (que fala Anthropic/Gemini API-key ou OpenAI-compat HTTP).")
        fb_p = env.get("HIVE_CLAUDE_MEM_FALLBACK_PROVIDER", "").strip()
        fb_m = env.get("HIVE_CLAUDE_MEM_FALLBACK_MODEL", "").strip()
        if fb_p and fb_m and _usable_by_claude_mem(fb_p, PROVIDERS_CONFIG.get(fb_p.lower(), {})):
            print(f"  -> usando fallback compatível '{fb_p}/{fb_m}'")
            provider, model = fb_p, fb_m
        else:
            print("X Nenhum provider compatível disponível para o claude-mem. "
                  "Configure HIVE_CLAUDE_MEM_PROVIDER/MODEL (ou FALLBACK) com um "
                  "provider HTTP+chave (nvidia, ollama, openrouter, deepseek…) ou "
                  "os slots nativos gemini/claude (API key). Config viva preservada.")
            return 1

    updates = build_updates(provider, model, env)
    chain = build_provider_chain(env)
    if chain:
        updates["CLAUDE_MEM_PROVIDER_CHAIN"] = json.dumps(
            chain, ensure_ascii=False, separators=(",", ":")
        )
    safe = {k: ("***" if "KEY" in k or "TOKEN" in k or k == "CLAUDE_MEM_PROVIDER_CHAIN" else v) for k, v in updates.items()}
    print(f"claude-mem <- {provider}/{model}")
    print(json.dumps(safe, indent=2))

    if "--print" in sys.argv:
        return 0

    apply(updates)
    print("OK aplicado via /api/settings (live) + seed global ~/.claude-mem")
    if "CLAUDE_MEM_OPENROUTER_BASE_URL" in updates and "--no-restart" not in sys.argv:
        restart_worker()
        print("OK worker reiniciado (base_url do slot OpenAI-compat aplicado)")

    fb_provider = env.get("HIVE_CLAUDE_MEM_FALLBACK_PROVIDER", "").strip()
    fb_model = env.get("HIVE_CLAUDE_MEM_FALLBACK_MODEL", "").strip()
    if fb_provider and fb_model:
        print(f"  i Fallback disponível: {fb_provider}/{fb_model} (activa quando quota esgotar)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
