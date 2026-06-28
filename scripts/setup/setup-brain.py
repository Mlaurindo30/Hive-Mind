#!/usr/bin/env python3
"""
Hive-Mind — Brain Selector & Auto-Discovery
Interface unificada para configurar chaves e escolher modelos em tempo real.
Suporta configuração de LLM por papel (Dreamer, Graphify, Vision, Síntese P2P)
com herança do Dreamer e fallback opcional por papel.
"""

import os
import sys
import json
import requests
import webbrowser
import re
import shutil
from pathlib import Path
from typing import Dict, Any, List
from pydantic import BaseModel

# Configura paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

from core.auth import (
    PROVIDERS_CONFIG,
    discover_models_realtime,
    gemini_cli_oauth_file,
    get_credentials,
    get_role_config,
    get_oauth_credentials,
    load_env,
    poll_oauth_token,
    save_env,
)

# Cores ANSI para uma interface profissional
GREEN = "\033[0;32m"; YELLOW = "\033[1;33m"; BLUE = "\033[1;34m"; RED = "\033[0;31m"
BOLD = "\033[1m"; NC = "\033[0m"
DIM = "\033[2m"
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

# Papéis configuráveis (id, rótulo). O Dreamer é a base de herança dos demais:
# configurar o Dreamer (primário + fb1 + fb2) já propaga p/ TODOS os papéis abaixo.
# Configure um papel individual só se quiser sobrescrever a herança.
ROLES = [
    ("dreamer",   "Dreamer (pipeline principal — BASE de herança)"),
    ("graphify",  "Graphify (grafo de conhecimento)"),
    ("vision",    "Vision (estágio visual)"),
    ("synthesis", "Síntese P2P (dialética)"),
    ("claude_mem", "Claude Mem (Memória & Discovery)"),
    # Fase 2 (memória inteligente)
    ("weekly_synthesizer", "Weekly Synthesizer (resumo semanal)"),
    ("monthly_synthesizer", "Monthly Synthesizer (resumo mensal)"),
    ("yearly_synthesizer", "Yearly Synthesizer (resumo anual)"),
    ("alias_miner",        "Alias Miner (slugs)"),
    ("sector_classifier",  "Sector Classifier (setores)"),
    ("topic_router",       "Topic Router (roteamento de tópicos)"),
    # Fase 3-4 (síntese viva / executiva)
    ("pattern_distiller",  "Pattern Distiller (memória procedural)"),
    ("conflict_detector",  "Conflict Detector (contradições)"),
    ("session_summarizer", "Session Summarizer (sessões)"),
    ("daily_writer",       "Daily Writer (diário)"),
]

# Papéis de extração SEMPRE locais (Ollama): grafo temporal (Graphiti) e RAG
# vetorial (LightRAG). Não passam pela máquina de providers/fallback — os
# clientes leem só HIVE_{ROLE}_MODEL. Configurados no menu "Extração local".
# (id, rótulo, env_var, default). Presets sugeridos em LOCAL_MODEL_PRESETS.
LOCAL_EXTRACTION_ROLES = [
    ("graphiti", "Graphiti (grafo temporal — entidades/relações)", "HIVE_GRAPHITI_MODEL", "qwen2.5:3b"),
    ("lightrag", "LightRAG (RAG vetorial — extração)",             "HIVE_LIGHTRAG_MODEL", "qwen2.5:3b"),
]

# Modelos Ollama locais sugeridos para extração (ordem = preferência).
LOCAL_MODEL_PRESETS = [
    ("qwen2.5:3b", "padrão — multilíngue PT/EN, ~1.9GB, rápido, cabe na GPU c/ embedder 1024d"),
    ("qwen2.5:7b", "alta qualidade — ~4.7GB, exige folga de VRAM (recomendado p/ Graphiti)"),
    ("granite3-dense:2b", "legado — leve mas alucina entidades; evite"),
]

def clear(): os.system('clear' if os.name == 'posix' else 'cls')


def term_width() -> int:
    return max(92, min(140, shutil.get_terminal_size((110, 24)).columns))


def plain(text: str) -> str:
    return ANSI_RE.sub("", str(text))


def fit(text: str, width: int) -> str:
    text = str(text)
    raw = plain(text)
    if len(raw) <= width:
        return text + (" " * (width - len(raw)))
    clipped = raw[: max(1, width - 1)] + "…"
    return clipped


def line(char: str = "─") -> str:
    return char * term_width()


def header(title: str, subtitle: str | None = None) -> None:
    w = term_width()
    print(f"{BOLD}{BLUE}{'=' * w}{NC}")
    print(f"{BOLD}{BLUE}{title}{NC}")
    if subtitle:
        print(f"{DIM}{subtitle}{NC}")
    print(f"{BOLD}{BLUE}{'=' * w}{NC}")

def role_var(role: str, suffix: str) -> str:
    return f"HIVE_{role.upper()}_{suffix}"


def role_config_parts(role: str, env: Dict[str, str]) -> tuple[str, str, str]:
    p = env.get(role_var(role, "PROVIDER"))
    m = env.get(role_var(role, "MODEL"))
    if p and m:
        primary = f"{GREEN}{m}{NC} {DIM}({p}){NC}"
    elif role == "dreamer":
        primary = f"{YELLOW}não configurado{NC}"
    else:
        primary = f"{BLUE}herda Dreamer{NC}"

    fb_p = env.get(role_var(role, "FALLBACK_PROVIDER"))
    fb_m = env.get(role_var(role, "FALLBACK_MODEL"))
    fb1 = f"{fb_m} {DIM}({fb_p}){NC}" if fb_p and fb_m else f"{DIM}- {NC}"

    fb2_p = env.get(role_var(role, "FALLBACK2_PROVIDER"))
    fb2_m = env.get(role_var(role, "FALLBACK2_MODEL"))
    fb2 = f"{fb2_m} {DIM}({fb2_p}){NC}" if fb2_p and fb2_m else f"{DIM}- {NC}"
    return primary, fb1, fb2


def provider_auth_label(p_name: str) -> str:
    cfg = PROVIDERS_CONFIG[p_name]
    if "gemini_cli_oauth" in cfg["auth_type"]:
        return "CLI OAuth"
    if "local" in cfg["auth_type"]:
        return "local"
    if "api_key" in cfg["auth_type"] and "oauth" in cfg["auth_type"]:
        return "api key/OAuth"
    return "api key"


def provider_source_label(p_name: str, env: Dict[str, str]) -> str:
    cfg = PROVIDERS_CONFIG[p_name]
    if "gemini_cli_oauth" in cfg["auth_type"]:
        oauth_file = gemini_cli_oauth_file()
        return f"CLI externo: {oauth_file}" if oauth_file else "CLI externo: login pendente"
    if "local" in cfg["auth_type"]:
        return cfg.get("base_url", "local")
    token = env.get(f"{p_name.upper()}_ACCESS_TOKEN")
    key = env.get(cfg["env_var"]) or env.get(cfg.get("alt_env_var", ""))
    if token:
        return f"OAuth no .env ({_mask_secret(token)})"
    if key:
        return f"{cfg['env_var']} no .env ({_mask_secret(key)})"
    return "credencial ausente"


def model_source_label(model: Dict[str, Any], p_name: str) -> str:
    source = model.get("source")
    if source == "gemini_cli_oauth_models_hint":
        return "catalogo local liberado por OAuth"
    cfg = PROVIDERS_CONFIG[p_name]
    if "local" in cfg["auth_type"]:
        return "API local listada"
    if source:
        return source
    return "API remota listada"


def describe_role(role: str, env: Dict[str, str]) -> str:
    """Valor atual do papel: modelo próprio, 'herda do Dreamer' ou 'Nenhum'."""
    p = env.get(role_var(role, "PROVIDER"))
    m = env.get(role_var(role, "MODEL"))
    if p and m:
        desc = f"{GREEN}{m}{NC} ({p})"
    elif role == "dreamer":
        desc = f"{YELLOW}Nenhum{NC}"
    else:
        desc = f"{BLUE}herda do Dreamer{NC}"
    fb_p = env.get(role_var(role, "FALLBACK_PROVIDER"))
    fb_m = env.get(role_var(role, "FALLBACK_MODEL"))
    if fb_p and fb_m:
        desc += f" | fb1: {fb_m} ({fb_p})"
    fb2_p = env.get(role_var(role, "FALLBACK2_PROVIDER"))
    fb2_m = env.get(role_var(role, "FALLBACK2_MODEL"))
    if fb2_p and fb2_m:
        desc += f" | fb2: {fb2_m} ({fb2_p})"
    return desc


# Sufixo de variável por nível de fallback (0=primário, 1=fallback, 2=rede final).
_LEVEL_PREFIX = {0: "", 1: "FALLBACK_", 2: "FALLBACK2_"}
_LEVEL_LABEL = {0: "papel", 1: "1º FALLBACK", 2: "2º FALLBACK (rede final)"}

def is_provider_configured(p_name: str, env: Dict[str, str]) -> bool:
    cfg = PROVIDERS_CONFIG[p_name]
    # antigravity / gemini-cli: configurado = existe o login OAuth do CLI no disco.
    if "gemini_cli_oauth" in cfg["auth_type"]:
        return gemini_cli_oauth_file() is not None
    # antigravity-cli (`agy`): configurado = binário presente + mesmo OAuth de ~/.gemini.
    if "agy_cli" in cfg["auth_type"]:
        from pathlib import Path as _P
        return _P(os.environ.get("AGY_BIN", str(_P.home() / ".local/bin/agy"))).exists() \
            and gemini_cli_oauth_file() is not None
    if "oauth" in cfg["auth_type"]:
        if f"{p_name.upper()}_ACCESS_TOKEN" in env: return True
    if cfg['env_var'] in env or "local" in cfg['auth_type']:
        return True
    return False

def main_menu():
    while True:
        clear()
        header("HIVE-MIND: SELETOR DE INTELIGENCIA", "Dashboard compacto: papel, primario e fallbacks efetivos.")

        env = load_env()
        print(f"\n{BOLD}Papeis configurados{NC}")
        print(line())
        print(f"{BOLD}{fit('#', 4)} {fit('Papel', 30)} {fit('Primario', 34)} {fit('Fallback 1', 28)} {fit('Fallback 2', 28)}{NC}")
        print(line("-"))
        for i, (rid, label) in enumerate(ROLES):
            primary, fb1, fb2 = role_config_parts(rid, env)
            print(f"{fit(str(i+1), 4)} {fit(label, 30)} {fit(primary, 34)} {fit(fb1, 28)} {fit(fb2, 28)}")

        # Extração local (Ollama-only): Graphiti + LightRAG
        print(line("-"))
        print(f"{BOLD}Extração local (Ollama){NC}")
        for rid, label, var, default in LOCAL_EXTRACTION_ROLES:
            cur = env.get(var) or f"{default} {DIM}(default){NC}"
            print(f"{fit('  ' + label, 50)} {GREEN}{cur}{NC}")

        print(line("-"))
        print(f"{fit('S', 4)} Saude dos providers")
        print(f"{fit('R', 4)} Resumo efetivo por papel")
        print(f"{fit('G', 4)} Extração local (Graphiti/LightRAG)")
        print(f"{fit('0', 4)} Sair")

        choice = input(f"\nSelecione um papel, S, R, G ou 0: ").strip()
        if choice == "0": break
        if choice.lower() == "s":
            providers_health_screen()
            continue
        if choice.lower() == "r":
            effective_summary_screen()
            continue
        if choice.lower() == "g":
            local_extraction_menu()
            continue

        try:
            role = ROLES[int(choice)-1][0]
            provider_menu(role)
        except (ValueError, IndexError):
            pass


def _ollama_installed_models() -> set[str]:
    """Modelos atualmente baixados no Ollama local (vazio se Ollama off)."""
    base = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    try:
        resp = requests.get(f"{base}/api/tags", timeout=3)
        resp.raise_for_status()
        return {m.get("name", "") for m in resp.json().get("models", [])}
    except Exception:
        return set()


def local_extraction_menu():
    """Configura os modelos Ollama locais de extração (Graphiti / LightRAG).

    Estes papéis não usam a máquina de providers: gravamos só HIVE_{ROLE}_MODEL,
    que os clientes (integrations/graphiti/client.py, core/lightrag_index.py)
    leem direto. Default qwen2.5:3b; opção qwen2.5:7b p/ Graphiti alta qualidade.
    """
    while True:
        clear()
        header("EXTRAÇÃO LOCAL (OLLAMA)", "Graphiti (grafo temporal) e LightRAG (RAG vetorial) — sempre local.")
        env = load_env()
        installed = _ollama_installed_models()

        print(f"\n{BOLD}Papéis de extração local{NC}")
        print(line("-"))
        for i, (rid, label, var, default) in enumerate(LOCAL_EXTRACTION_ROLES):
            cur = env.get(var)
            shown = cur or f"{default} (default)"
            mark = f"{GREEN}✓ baixado{NC}" if (cur or default) in installed else f"{YELLOW}⊘ não baixado{NC}"
            print(f"{fit(str(i+1), 4)} {fit(label, 46)} {fit(shown, 22)} {mark}")
        print(line("-"))
        print(f"{fit('0', 4)} Voltar")

        choice = input(f"\nSelecione um papel (1-{len(LOCAL_EXTRACTION_ROLES)}) ou 0: ").strip()
        if choice == "0":
            return
        try:
            rid, label, var, default = LOCAL_EXTRACTION_ROLES[int(choice) - 1]
        except (ValueError, IndexError):
            continue
        _local_model_picker(rid, label, var, default, installed)


def _local_model_picker(rid: str, label: str, var: str, default: str, installed: set[str]):
    clear()
    header(f"MODELO LOCAL: {label}", f"Grava {var} no .env (Ollama local).")
    print(f"\n{BOLD}Presets sugeridos:{NC}")
    print(line("-"))
    for i, (model, note) in enumerate(LOCAL_MODEL_PRESETS):
        mark = f"{GREEN}✓{NC}" if model in installed else f"{YELLOW}⊘{NC}"
        print(f"{fit(str(i+1), 4)} {mark} {fit(model, 22)} {DIM}{note}{NC}")
    print(line("-"))
    print(f"{fit('C', 4)} Customizado (digitar nome do modelo)")
    print(f"{fit('D', 4)} Restaurar default ({default})")
    print(f"{fit('0', 4)} Voltar")

    choice = input("\nEscolha: ").strip().lower()
    if choice == "0":
        return
    if choice == "d":
        save_env(var, default)
        print(f"{GREEN}✓{NC} {var} = {default} (default)")
    elif choice == "c":
        model = input("Nome do modelo Ollama (ex.: qwen2.5:7b): ").strip()
        if model:
            save_env(var, model)
            print(f"{GREEN}✓{NC} {var} = {model}")
            if model not in installed:
                print(f"{YELLOW}⚠{NC} {model} ainda não está baixado. Rode: ollama pull {model}")
    else:
        try:
            model = LOCAL_MODEL_PRESETS[int(choice) - 1][0]
        except (ValueError, IndexError):
            return
        save_env(var, model)
        print(f"{GREEN}✓{NC} {var} = {model}")
        if model not in installed:
            print(f"{YELLOW}⚠{NC} {model} ainda não está baixado. Rode: ollama pull {model}")
    input("\nEnter para continuar...")

def provider_menu(role: str, level: int = 0):
    clear()
    header(f"CONFIGURANDO {role.upper()}", f"Alvo: {_LEVEL_LABEL[level]}")

    env = load_env()
    active_provider = env.get("HIVE_DREAMER_PROVIDER", "Nenhum")
    active_model = env.get("HIVE_DREAMER_MODEL", "Nenhum")
    if role != "dreamer" or level > 0:
        print(f"\n{BOLD}Base herdada do Dreamer:{NC} {GREEN}{active_model}{NC} {DIM}({active_provider}){NC}")
        print(line("-"))

    print(f"\n{BOLD}Provedores Disponíveis:{NC}")
    # 'google' (API key/OAuth Generative Language) está aposentado: o token OAuth
    # não renova mais de forma confiável e a key direta foi descontinuada no setup.
    # O acesso Gemini é feito via gemini-cli/antigravity (CLI OAuth). Ocultado do
    # menu para não ser oferecido/configurado; o code path permanece por compat.
    _HIDDEN_PROVIDERS = {"google"}
    providers = [p for p in PROVIDERS_CONFIG.keys() if p not in _HIDDEN_PROVIDERS]
    print(f"{BOLD}{fit('#', 4)} {fit('Provider', 16)} {fit('Auth', 18)} {fit('Status', 24)} {fit('Observacao', 36)}{NC}")
    print(line("-"))
    for i, p in enumerate(providers):
        cfg = PROVIDERS_CONFIG[p]
        if "agy_cli" in cfg["auth_type"]:
            auth = "agy CLI"
            status = f"{GREEN}configurado{NC}" if is_provider_configured(p, env) else f"{YELLOW}pendente{NC}"
            note = "subprocess agy (claude/gpt-oss)"
        elif "gemini_cli_oauth" in cfg["auth_type"]:
            auth = "CLI OAuth"
            status = f"{GREEN}configurado{NC}" if is_provider_configured(p, env) else f"{YELLOW}pendente{NC}"
            note = "login externo"
        elif "local" in cfg["auth_type"]:
            auth = "local"
            status = f"{GREEN}disponivel{NC}"
            note = cfg.get("base_url", "")
        elif "api_key" in cfg["auth_type"] and "oauth" in cfg["auth_type"]:
            auth = "api key / OAuth"
            status = f"{GREEN}configurado{NC}" if is_provider_configured(p, env) else f"{YELLOW}pendente{NC}"
            note = "menu gerencia credencial"
        else:
            auth = "api key"
            status = f"{GREEN}configurado{NC}" if is_provider_configured(p, env) else f"{YELLOW}pendente{NC}"
            note = ""
        print(f"{fit(str(i+1), 4)} {fit(p, 16)} {fit(auth, 18)} {fit(status, 24)} {fit(note, 36)}")

    print(line("-"))
    print(f"{fit('S', 4)} Saude dos providers")
    print(f"{fit('0', 4)} Voltar")

    choice = input(f"\nSelecione um Provedor (ou 0): ").strip()
    if choice == "0": return
    if choice.lower() == "s":
        providers_health_screen()
        return

    try:
        p_name = providers[int(choice)-1]
        manage_provider(p_name, role, level)
    except (ValueError, IndexError):
        pass

def _mask_secret(value: str) -> str:
    """Mascara um segredo para exibição (mostra prefixo/sufixo curtos)."""
    if not value:
        return ""
    if len(value) <= 10:
        return value[:2] + "…"
    return f"{value[:6]}…{value[-4:]}"

def describe_provider_credential(p_name: str, env: Dict[str, str]) -> str:
    """Descreve a credencial ativa do provedor (método + valor mascarado)."""
    cfg = PROVIDERS_CONFIG[p_name]
    if "gemini_cli_oauth" in cfg["auth_type"]:
        oauth_file = gemini_cli_oauth_file()
        if oauth_file:
            return f"CLI OAuth ({oauth_file})"
        return f"{YELLOW}CLI OAuth pendente — execute o CLI correspondente uma vez{NC}"
    token = env.get(f"{p_name.upper()}_ACCESS_TOKEN")
    key = env.get(cfg["env_var"]) or env.get(cfg.get("alt_env_var", ""))
    parts = []
    if token:
        parts.append(f"OAuth (conta logada, token {_mask_secret(token)})")
    if key:
        parts.append(f"API key {_mask_secret(key)}")
    if "local" in cfg["auth_type"] and not parts:
        parts.append("local (sem credencial)")
    return " + ".join(parts) if parts else f"{YELLOW}não configurado{NC}"


class _SetupBrainPing(BaseModel):
    ok: bool


def validate_provider_real(p_name: str, model: str | None = None) -> Dict[str, str]:
    """Executa validacao real e curta do provider.

    Nao simula sucesso: usa endpoint real de modelos ou, no caso Gemini CLI /
    Antigravity, faz uma geracao minima via o mesmo cliente usado em runtime.
    """
    cfg = PROVIDERS_CONFIG[p_name]
    started = __import__("time").time()

    def done(status: str, detail: str, source: str = "") -> Dict[str, str]:
        elapsed_ms = int((__import__("time").time() - started) * 1000)
        return {"status": status, "detail": detail, "source": source, "elapsed": f"{elapsed_ms}ms"}

    try:
        if "agy_cli" in cfg["auth_type"]:
            from core.agy_client import call_agy_structured

            test_model = model or (cfg.get("models_hint") or ["gemini-3.5-flash"])[0]
            out = call_agy_structured(
                "Responda apenas JSON valido: {\"ok\": true}",
                "Validacao operacional minima do Hive-Mind.",
                _SetupBrainPing,
                model=test_model,
                provider=p_name,
            )
            return done("OK" if out.ok else "ERRO", f"geracao real (agy) em {test_model}", provider_source_label(p_name, load_env()))

        if "gemini_cli_oauth" in cfg["auth_type"]:
            from core.gemini_cli_client import call_gemini_cli_structured

            test_model = model or (cfg.get("models_hint") or ["gemini-2.5-flash"])[0]
            out = call_gemini_cli_structured(
                "Responda apenas JSON valido: {\"ok\": true}",
                "Validacao operacional minima do Hive-Mind.",
                _SetupBrainPing,
                model=test_model,
                provider=p_name,
            )
            return done("OK" if out.ok else "ERRO", f"geracao real em {test_model}", provider_source_label(p_name, load_env()))

        creds = get_credentials(p_name)
        if not creds:
            return done("PENDENTE", "credencial ausente", provider_source_label(p_name, load_env()))

        if p_name == "google":
            url = f"{creds['url']}/models"
            headers = {}
            if creds["type"] == "oauth":
                headers["Authorization"] = f"Bearer {creds['key']}"
            else:
                url += f"?key={creds['key']}"
            resp = requests.get(url, headers=headers, timeout=10)
        else:
            url = f"{creds['url']}/models"
            headers = {"Authorization": f"Bearer {creds['key']}"} if creds["type"] == "api_key" else {}
            resp = requests.get(url, headers=headers, timeout=10)

        if resp.ok:
            return done("OK", f"GET /models -> HTTP {resp.status_code}", provider_source_label(p_name, load_env()))
        if resp.status_code in (401, 403):
            return done(str(resp.status_code), "auth/licenca negada", resp.text[:160])
        if resp.status_code == 429:
            return done("429", "quota/rate limit", resp.text[:160])
        return done(str(resp.status_code), resp.text[:180])
    except requests.Timeout:
        return done("TIMEOUT", "timeout na chamada real")
    except Exception as exc:
        msg = str(exc)
        if "429" in msg or "Resource has been exhausted" in msg:
            return done("429", msg[:180])
        if any(code in msg for code in ("401", "403", "authentication failed", "SUBSCRIPTION_REQUIRED")):
            return done("AUTH", msg[:180])
        return done("ERRO", msg[:180])


def providers_health_screen(selected: str | None = None):
    clear()
    header("SAUDE DOS PROVIDERS", "Auth, status, origem da credencial e validacao real sob demanda.")
    env = load_env()
    providers = list(PROVIDERS_CONFIG.keys())
    if selected and selected in providers:
        providers = [selected]

    print(f"\n{BOLD}{fit('#', 4)} {fit('Provider', 16)} {fit('Auth', 14)} {fit('Status', 14)} {fit('Origem da credencial', 58)}{NC}")
    print(line("-"))
    for i, p in enumerate(providers):
        status = f"{GREEN}configurado{NC}" if is_provider_configured(p, env) else f"{YELLOW}pendente{NC}"
        print(f"{fit(str(i+1), 4)} {fit(p, 16)} {fit(provider_auth_label(p), 14)} {fit(status, 14)} {fit(provider_source_label(p, env), 58)}")
    print(line("-"))
    print(f"{fit('A', 4)} Validar todos agora")
    print(f"{fit('0', 4)} Voltar")

    choice = input("\nValidar provider numero, A ou 0: ").strip()
    if choice == "0":
        return
    targets: list[str] = []
    if choice.lower() == "a":
        targets = providers
    else:
        try:
            targets = [providers[int(choice) - 1]]
        except (ValueError, IndexError):
            return

    print(f"\n{BOLD}Validacao real{NC}")
    print(line("-"))
    print(f"{BOLD}{fit('Provider', 16)} {fit('Resultado', 12)} {fit('Tempo', 10)} {fit('Detalhe', 78)}{NC}")
    print(line("-"))
    for p in targets:
        result = validate_provider_real(p)
        color = GREEN if result["status"] == "OK" else (YELLOW if result["status"] in ("PENDENTE", "429", "TIMEOUT") else RED)
        detail = result["detail"] if not result.get("source") else f"{result['detail']} | {result['source']}"
        print(f"{fit(p, 16)} {fit(color + result['status'] + NC, 12)} {fit(result['elapsed'], 10)} {fit(detail, 78)}")
    input("\nEnter para voltar...")


def effective_summary_screen():
    clear()
    header("RESUMO EFETIVO", "Cadeia resolvida por papel, incluindo heranca do Dreamer e fallbacks.")
    env = load_env()
    for key, value in env.items():
        os.environ.setdefault(key, value)
    print(f"\n{BOLD}{fit('Papel', 30)} {fit('Primario efetivo', 36)} {fit('Fallback 1', 30)} {fit('Fallback 2', 30)}{NC}")
    print(line("-"))
    for rid, label in ROLES:
        cfg = get_role_config(rid) or {}
        own = bool(env.get(role_var(rid, "PROVIDER")) and env.get(role_var(rid, "MODEL")))
        inherited = rid != "dreamer" and not own and cfg
        p = cfg.get("provider")
        m = cfg.get("model")
        fb_p = cfg.get("fallback_provider")
        fb_m = cfg.get("fallback_model")
        fb2_p = cfg.get("fallback2_provider")
        fb2_m = cfg.get("fallback2_model")
        primary = f"{m} ({p})" if p and m else "nao configurado"
        if inherited:
            primary += " [herda Dreamer]"
        fb1 = f"{fb_m} ({fb_p})" if fb_p and fb_m else "-"
        fb2 = f"{fb2_m} ({fb2_p})" if fb2_p and fb2_m else "-"
        print(f"{fit(label, 30)} {fit(primary, 36)} {fit(fb1, 30)} {fit(fb2, 30)}")
    input("\nEnter para voltar...")

def _oauth_login(p_name: str) -> bool:
    """Executa o fluxo OAuth interativo. Retorna True em sucesso.

    Como o auth_url usa prompt=consent, re-logar permite escolher OUTRA conta.
    """
    clear()
    print(f"{BOLD}{BLUE}Iniciando fluxo OAuth para {p_name.upper()}...{NC}")
    init_data = get_oauth_credentials(p_name)
    if not init_data or "error" in init_data:
        msg = init_data.get('error', 'Falha ao iniciar') if init_data else 'Falha ao iniciar'
        print(f"{RED}Erro: {msg}{NC}")
        input("\nEnter para voltar...")
        return False

    if init_data.get("type") == "loopback":
        print(f"\n{YELLOW}Abrindo navegador para autorização...{NC}")
        print(f"Se não abrir automaticamente, acesse:\n{BOLD}{init_data['auth_url']}{NC}")
        webbrowser.open(init_data['auth_url'])
        print(f"\n{BLUE}Aguardando aprovação no Localhost...{NC}")
    else:
        print(f"\n1. Acesse: {BOLD}{YELLOW}{init_data['verification_url']}{NC}")
        print(f"2. Digite o código: {BOLD}{GREEN}{init_data['user_code']}{NC}")
        print(f"\n{BLUE}Aguardando autorização (esta janela será atualizada)...{NC}")

    token_data = poll_oauth_token(p_name, init_data)
    if "error" in token_data:
        print(f"{RED}Falha: {token_data['error']}{NC}")
        input("\nEnter para voltar...")
        return False
    print(f"\n{GREEN}✓ Login realizado com sucesso!{NC}")
    return True

def _api_key_entry(p_name: str) -> bool:
    """Pede e salva a API key do provedor. Retorna True em sucesso."""
    cfg = PROVIDERS_CONFIG[p_name]
    clear()
    print(f"{BOLD}--- API Key de {p_name.upper()} ---{NC}")
    print(f"Obtenha sua chave em: {YELLOW}{cfg['doc']}{NC}")
    key = input(f"\nInsira a API Key (ou Enter para cancelar): ").strip()
    if not key:
        return False
    save_env(cfg['env_var'], key)
    os.environ[cfg['env_var']] = key
    print(f"{GREEN}✓ Chave salva!{NC}")
    return True

def _clear_credentials(p_name: str):
    """Remove tokens OAuth e API key do provedor no .env e no ambiente."""
    cfg = PROVIDERS_CONFIG[p_name]
    for var in (f"{p_name.upper()}_ACCESS_TOKEN", f"{p_name.upper()}_REFRESH_TOKEN",
                cfg["env_var"], cfg.get("alt_env_var", "")):
        if not var:
            continue
        save_env(var, "")
        os.environ.pop(var, None)

def configured_provider_menu(p_name: str, role: str, level: int = 0):
    """Menu para provedor JÁ configurado: trocar API key, re-logar OAuth, remover."""
    cfg = PROVIDERS_CONFIG[p_name]
    while True:
        clear()
        env = load_env()
        print(f"{BOLD}{BLUE}--- {p_name.upper()} (já configurado) ---{NC}")
        print(f"\nCredencial atual: {describe_provider_credential(p_name, env)}")
        print("-" * 50)
        print(f"\n  1) Usar / escolher modelo")
        opts = {"1": "models"}
        n = 2
        print(f"  {n}) Validar agora (chamada real minima)")
        opts[str(n)] = "validate"; n += 1
        if "api_key" in cfg["auth_type"]:
            print(f"  {n}) Trocar a API key")
            opts[str(n)] = "api_key"; n += 1
        if "oauth" in cfg["auth_type"]:
            print(f"  {n}) Re-logar OAuth (entrar com OUTRA conta)")
            opts[str(n)] = "oauth"; n += 1
        print(f"  {n}) Remover credenciais deste provedor")
        opts[str(n)] = "remove"
        print(f"\n  0) Voltar")

        choice = input(f"\nEscolha: ").strip()
        if choice == "0":
            return
        action = opts.get(choice)
        if action == "models":
            show_model_selection(p_name, role, level)
            return
        elif action == "validate":
            result = validate_provider_real(p_name)
            color = GREEN if result["status"] == "OK" else (YELLOW if result["status"] in ("PENDENTE", "429", "TIMEOUT") else RED)
            print(f"\nResultado: {color}{result['status']}{NC} ({result['elapsed']})")
            print(f"Detalhe: {result['detail']}")
            if result.get("source"):
                print(f"Origem: {result['source']}")
            input("\nEnter para continuar...")
        elif action == "api_key":
            _api_key_entry(p_name)
            input("\nEnter para continuar...")
        elif action == "oauth":
            # Re-login: limpa tokens antigos para forçar nova autorização/conta.
            save_env(f"{p_name.upper()}_ACCESS_TOKEN", "")
            save_env(f"{p_name.upper()}_REFRESH_TOKEN", "")
            os.environ.pop(f"{p_name.upper()}_ACCESS_TOKEN", None)
            os.environ.pop(f"{p_name.upper()}_REFRESH_TOKEN", None)
            _oauth_login(p_name)
            input("\nEnter para continuar...")
        elif action == "remove":
            confirm = input(f"{YELLOW}Remover TODAS as credenciais de {p_name}? (s/N): {NC}").strip().lower()
            if confirm in ("s", "sim", "y", "yes"):
                _clear_credentials(p_name)
                print(f"{GREEN}✓ Credenciais removidas.{NC}")
                input("\nEnter para continuar...")
                return

def manage_provider(p_name: str, role: str, level: int = 0):
    cfg = PROVIDERS_CONFIG[p_name]
    env = load_env()

    # Provedor JÁ configurado → menu de gestão (trocar key, re-logar, remover, usar)
    if is_provider_configured(p_name, env):
        configured_provider_menu(p_name, role, level)
        return

    # Provedor novo → escolhe método de auth e autentica
    auth_types = cfg["auth_type"]
    selected_auth = auth_types[0]

    if len(auth_types) > 1:
        clear()
        print(f"{BOLD}--- Métodos de Autenticação para {p_name.upper()} ---{NC}")
        for i, t in enumerate(auth_types):
            print(f"  {i+1}) {t.upper()}")
        method_choice = input(f"\nEscolha o método (padrão 1): ").strip()
        if method_choice:
            try: selected_auth = auth_types[int(method_choice)-1]
            except: pass

    if selected_auth == "oauth":
        if not _oauth_login(p_name):
            return
    elif selected_auth == "api_key":
        if not _api_key_entry(p_name):
            return

    show_model_selection(p_name, role, level)


def sync_claude_mem_provider(expected_provider: str, expected_model: str) -> bool:
    """Aplica o papel claude_mem no worker real e confirma a config viva."""
    import subprocess

    cmd = (sys.executable, str(PROJECT_ROOT / "scripts" / "setup" / "sync-claude-mem-provider.py"))
    proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    if proc.stdout:
        print(proc.stdout.rstrip())
    if proc.stderr:
        print(proc.stderr.rstrip())
    if proc.returncode != 0:
        print(f"{RED}✗ sync claude-mem falhou com exit {proc.returncode}.{NC}")
        return False

    try:
        resp = requests.get("http://127.0.0.1:37700/api/settings", timeout=5)
        resp.raise_for_status()
        settings = resp.json()
    except Exception as exc:
        print(f"{YELLOW}⚠ não consegui confirmar /api/settings após sync: {exc}{NC}")
        return False

    provider = expected_provider.lower()
    if provider in ("anthropic", "claude"):
        ok = (
            settings.get("CLAUDE_MEM_PROVIDER") == "claude"
            and settings.get("CLAUDE_MEM_MODEL") == expected_model
        )
    elif provider in ("google", "gemini"):
        ok = (
            settings.get("CLAUDE_MEM_PROVIDER") == "gemini"
            and settings.get("CLAUDE_MEM_GEMINI_MODEL") == expected_model
        )
    else:
        ok = (
            settings.get("CLAUDE_MEM_PROVIDER") == "openrouter"
            and settings.get("CLAUDE_MEM_OPENROUTER_MODEL") == expected_model
        )

    if ok:
        print(f"{GREEN}✓ claude-mem confirmado no worker: {expected_provider}/{expected_model}{NC}")
        return True

    live = {
        "CLAUDE_MEM_PROVIDER": settings.get("CLAUDE_MEM_PROVIDER"),
        "CLAUDE_MEM_MODEL": settings.get("CLAUDE_MEM_MODEL"),
        "CLAUDE_MEM_GEMINI_MODEL": settings.get("CLAUDE_MEM_GEMINI_MODEL"),
        "CLAUDE_MEM_OPENROUTER_MODEL": settings.get("CLAUDE_MEM_OPENROUTER_MODEL"),
    }
    print(f"{RED}✗ claude-mem não aplicou o modelo esperado.{NC}")
    print(json.dumps(live, indent=2))
    return False


def show_model_selection(p_name: str, role: str, level: int = 0):
    clear()
    header(f"MODELOS: {p_name.upper()}", f"Alvo: {_LEVEL_LABEL[level]} {role.upper()}")

    all_models = discover_models_realtime(only_provider=p_name)
    p_models = [m for m in all_models if m['provider'] == p_name]

    if not p_models:
        print(f"\n{RED}✗ Nenhum modelo encontrado.{NC}")
        cfg = PROVIDERS_CONFIG[p_name]
        if "gemini_cli_oauth" in cfg["auth_type"]:
            print("Este provedor usa login do CLI externo.")
            print("Execute `gemini` ou `agy` uma vez para autenticar e volte para este menu.")
            hints = cfg.get("models_hint", [])
            if hints:
                print("\nModelos esperados quando o CLI OAuth estiver disponível:")
                for m in hints:
                    print(f"  - {m}")
        else:
            print(f"Dica: Se você acabou de logar, tente 'Re-autenticar' no menu do provedor.")
        print("-" * 30)
        print(f"1) Tentar novamente")
        print(f"2) Re-configurar / Re-logar")
        print(f"0) Voltar")
        choice = input("\nEscolha: ")
        if choice == "1": show_model_selection(p_name, role, level)
        elif choice == "2":
            # Força remoção de tokens/chaves para re-configurar
            env = load_env()
            cfg = PROVIDERS_CONFIG[p_name]
            if f"{p_name.upper()}_ACCESS_TOKEN" in env: save_env(f"{p_name.upper()}_ACCESS_TOKEN", "")
            if cfg['env_var'] in env: save_env(cfg['env_var'], "")
            manage_provider(p_name, role, level)
        return

    print(f"\n{BOLD}Modelos detectados em {p_name}:{NC}")
    source = p_models[0].get("source") if p_models else None
    if source == "gemini_cli_oauth_models_hint":
        print(f"{DIM}Origem: catálogo do provider liberado pelo login CLI OAuth local.{NC}")
    print(line("-"))
    print(f"{BOLD}{fit('#', 4)} {fit('Modelo', 44)} {fit('Fonte', 42)}{NC}")
    print(line("-"))
    for i, m in enumerate(p_models):
        print(f"{fit(str(i+1), 4)} {fit(m['id'], 44)} {fit(model_source_label(m, p_name), 42)}")
    print(line("-"))
    print(f"{fit('0', 4)} Voltar")

    m_choice = input(f"\nEscolha o modelo: ")
    if m_choice == "0": return

    try:
        selected = p_models[int(m_choice)-1]
    except (ValueError, IndexError):
        return

    prefix = _LEVEL_PREFIX[level]
    save_env(role_var(role, f"{prefix}PROVIDER"), selected['provider'])
    save_env(role_var(role, f"{prefix}MODEL"), selected['id'])
    target = f"{_LEVEL_LABEL[level]} {role.upper()}"
    print(f"\n{GREEN}{BOLD}✓ Hive-Mind atualizado ({target}): {selected['id']}{NC}")

    # Papel claude_mem: aplica a escolha direto no claude-mem (settings.json) e
    # reinicia o worker, para o claude-mem passar a gerar com o modelo escolhido.
    if role == "claude_mem" and level == 0:
        sync_claude_mem_provider(selected["provider"], selected["id"])

    if level < 2:
        prox = "FALLBACK" if level == 0 else "2º FALLBACK (rede final, ex.: OmniRoute)"
        ask = input(f"\nDefinir um {prox} para o papel {role.upper()}? (s/N — Enter pula): ").strip().lower()
        if ask in ("s", "sim", "y", "yes"):
            provider_menu(role, level=level + 1)
            return
    input("\nEnter para continuar...")

if __name__ == "__main__":
    try: main_menu()
    except KeyboardInterrupt:
        print(f"\n\n{YELLOW}Saindo...{NC}")
        sys.exit(0)
