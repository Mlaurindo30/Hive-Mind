#!/usr/bin/env python3
"""
Hive-Mind — Brain Selector & Auto-Discovery
Interface unificada para configurar chaves e escolher modelos em tempo real.
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

def clear(): os.system('clear' if os.name == 'posix' else 'cls')

def is_provider_configured(p_name: str, env: Dict[str, str]) -> bool:
    cfg = PROVIDERS_CONFIG[p_name]
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
        active_provider = env.get("HIVE_DREAMER_PROVIDER", "Nenhum")
        active_model = env.get("HIVE_DREAMER_MODEL", "Nenhum")
        
        print(f"\n{BOLD}Cérebro Atual:{NC} {GREEN}{active_model}{NC} ({active_provider})")
        print("-" * 50)
        
        print(f"\n{BOLD}Provedores Disponíveis:{NC}")
        providers = list(PROVIDERS_CONFIG.keys())
        for i, p in enumerate(providers):
            status = f"{GREEN}[CONFIGURADO]{NC}" if is_provider_configured(p, env) else f"{YELLOW}[PENDENTE]{NC}"
            print(f"  {i+1:2}) {p:15} {status}")
            
        print(f"\n  0) Sair")
        
        choice = input(f"\nSelecione um Provedor (ou 0): ")
        if choice == "0": break
        
        try:
            p_name = providers[int(choice)-1]
            manage_provider(p_name)
        except (ValueError, IndexError):
            pass

def manage_provider(p_name: str):
    cfg = PROVIDERS_CONFIG[p_name]
    env = load_env()
    
    # SE JÁ ESTIVER CONFIGURADO, VAI DIRETO PARA LISTAGEM DE MODELOS
    if is_provider_configured(p_name, env):
        show_model_selection(p_name)
        return

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
        clear()
        print(f"{BOLD}{BLUE}Iniciando fluxo OAuth para {p_name.upper()}...{NC}")
        init_data = get_oauth_credentials(p_name)
        
        if not init_data or "error" in init_data:
            print(f"{RED}Erro: {init_data.get('error', 'Falha ao iniciar')}{NC}")
            input("\nEnter para voltar...")
            return

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
            return
        print(f"\n{GREEN}✓ Login realizado com sucesso!{NC}")
        
    elif selected_auth == "api_key":
        clear()
        print(f"{BOLD}--- Configurando {p_name.upper()} ---{NC}")
        print(f"Obtenha sua chave em: {YELLOW}{cfg['doc']}{NC}")
        key = input(f"\nInsira a API Key (ou Enter para cancelar): ").strip()
        if not key: return
        save_env(cfg['env_var'], key)
        print(f"{GREEN}✓ Chave salva!{NC}")
        os.environ[cfg['env_var']] = key

    show_model_selection(p_name)

def show_model_selection(p_name: str):
    clear()
    print(f"{BOLD}{BLUE}🔍 Escaneando modelos em {p_name.upper()}...{NC}")
    
    all_models = discover_models_realtime()
    p_models = [m for m in all_models if m['provider'] == p_name]
    
    if not p_models:
        print(f"\n{RED}✗ Nenhum modelo encontrado.{NC}")
        print(f"Dica: Se você acabou de logar, tente 'Re-autenticar' no menu do provedor.")
        print("-" * 30)
        print(f"1) Tentar novamente")
        print(f"2) Re-configurar / Re-logar")
        print(f"0) Voltar")
        choice = input("\nEscolha: ")
        if choice == "1": show_model_selection(p_name)
        elif choice == "2":
            # Força remoção de tokens/chaves para re-configurar
            env = load_env()
            cfg = PROVIDERS_CONFIG[p_name]
            if f"{p_name.upper()}_ACCESS_TOKEN" in env: save_env(f"{p_name.upper()}_ACCESS_TOKEN", "")
            if cfg['env_var'] in env: save_env(cfg['env_var'], "")
            manage_provider(p_name)
        return

    print(f"\n{BOLD}Modelos detectados em {p_name}:{NC}")
    for i, m in enumerate(p_models):
        print(f"  {i+1:2}) {m['id']}")
    print(f"\n  0) Voltar")
    
    m_choice = input(f"\nEscolha o modelo: ")
    if m_choice == "0": return
    
    try:
        selected = p_models[int(m_choice)-1]
        save_env("HIVE_DREAMER_PROVIDER", selected['provider'])
        save_env("HIVE_DREAMER_MODEL", selected['id'])
        print(f"\n{GREEN}{BOLD}✓ Hive-Mind atualizado: {selected['id']}{NC}")
        input("\nEnter para continuar...")
    except: pass

if __name__ == "__main__":
    try: main_menu()
    except KeyboardInterrupt:
        print(f"\n\n{YELLOW}Saindo...{NC}")
        sys.exit(0)
