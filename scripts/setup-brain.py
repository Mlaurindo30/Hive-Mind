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
from pathlib import Path
from typing import Dict, Any, List

# Configura paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

from core.auth import PROVIDERS_CONFIG, save_env, load_env, discover_models_realtime, get_oauth_credentials, poll_oauth_token

# Cores ANSI para uma interface profissional
GREEN = "\033[0;32m"; YELLOW = "\033[1;33m"; BLUE = "\033[1;34m"; RED = "\033[0;31m"
BOLD = "\033[1m"; NC = "\033[0m"

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
    ("alias_miner",        "Alias Miner (slugs)"),
    ("sector_classifier",  "Sector Classifier (setores)"),
    ("topic_router",       "Topic Router (roteamento de tópicos)"),
    # Fase 3-4 (síntese viva / executiva)
    ("pattern_distiller",  "Pattern Distiller (memória procedural)"),
    ("conflict_detector",  "Conflict Detector (contradições)"),
    ("session_summarizer", "Session Summarizer (sessões)"),
    ("daily_writer",       "Daily Writer (diário)"),
]

def clear(): os.system('clear' if os.name == 'posix' else 'cls')

def role_var(role: str, suffix: str) -> str:
    return f"HIVE_{role.upper()}_{suffix}"

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
        from pathlib import Path
        return (Path.home() / ".gemini" / "oauth_creds.json").is_file()
    if "oauth" in cfg["auth_type"]:
        if f"{p_name.upper()}_ACCESS_TOKEN" in env: return True
    if cfg['env_var'] in env or "local" in cfg['auth_type']:
        return True
    return False

def main_menu():
    while True:
        clear()
        print(f"{BOLD}{BLUE}╔══════════════════════════════════════════════════════╗{NC}")
        print(f"{BOLD}{BLUE}║          🧠 HIVE-MIND: SELETOR DE INTELIGÊNCIA       ║{NC}")
        print(f"{BOLD}{BLUE}╚══════════════════════════════════════════════════════╝{NC}")

        env = load_env()
        print(f"\n{BOLD}Qual papel deseja configurar?{NC}")
        for i, (rid, label) in enumerate(ROLES):
            print(f"  {i+1}) {label:34} {describe_role(rid, env)}")

        print(f"\n  0) Sair")

        choice = input(f"\nSelecione um papel (ou 0): ").strip()
        if choice == "0": break

        try:
            role = ROLES[int(choice)-1][0]
            provider_menu(role)
        except (ValueError, IndexError):
            pass

def provider_menu(role: str, level: int = 0):
    clear()
    print(f"{BOLD}{BLUE}--- Configurando {_LEVEL_LABEL[level]} {role.upper()} ---{NC}")

    env = load_env()
    active_provider = env.get("HIVE_DREAMER_PROVIDER", "Nenhum")
    active_model = env.get("HIVE_DREAMER_MODEL", "Nenhum")
    print(f"\n{BOLD}Cérebro do Dreamer (base de herança):{NC} {GREEN}{active_model}{NC} ({active_provider})")
    print("-" * 50)

    print(f"\n{BOLD}Provedores Disponíveis:{NC}")
    providers = list(PROVIDERS_CONFIG.keys())
    for i, p in enumerate(providers):
        status = f"{GREEN}[CONFIGURADO]{NC}" if is_provider_configured(p, env) else f"{YELLOW}[PENDENTE]{NC}"
        print(f"  {i+1:2}) {p:15} {status}")

    print(f"\n  0) Voltar")

    choice = input(f"\nSelecione um Provedor (ou 0): ").strip()
    if choice == "0": return

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

def show_model_selection(p_name: str, role: str, level: int = 0):
    clear()
    print(f"{BOLD}{BLUE}🔍 Escaneando modelos em {p_name.upper()}...{NC}")

    all_models = discover_models_realtime(only_provider=p_name)
    p_models = [m for m in all_models if m['provider'] == p_name]

    if not p_models:
        print(f"\n{RED}✗ Nenhum modelo encontrado.{NC}")
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
    for i, m in enumerate(p_models):
        print(f"  {i+1:2}) {m['id']}")
    print(f"\n  0) Voltar")

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
        try:
            import subprocess
            subprocess.run(
                (sys.executable, str(PROJECT_ROOT / "scripts" / "sync-claude-mem-provider.py")),
                check=False,
            )
        except Exception as exc:  # nunca quebra o menu
            print(f"{YELLOW}⚠ sync claude-mem falhou: {exc}{NC}")

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
