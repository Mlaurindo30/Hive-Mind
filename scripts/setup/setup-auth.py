#!/usr/bin/env python3
"""
Hive-Mind — Assistente de Acesso e Auto-Descoberta
Replicando a inteligência de provedores do Hermes.
"""

import os
import sys
import json
from pathlib import Path

# Adiciona o diretório raiz ao path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

from core.auth import PROVIDERS_CONFIG, save_env, load_env

# Cores ANSI
GREEN = "\033[0;32m"; YELLOW = "\033[1;33m"; BLUE = "\033[1;34m"
BOLD = "\033[1m"; NC = "\033[0m"

def clear(): os.system('clear' if os.name == 'posix' else 'cls')

def main():
    while True:
        clear()
        print(f"{BOLD}{BLUE}╔══════════════════════════════════════════════════════╗{NC}")
        print(f"{BOLD}{BLUE}║           Hive-Mind: Gerenciador de Inteligência     ║{NC}")
        print(f"{BOLD}{BLUE}╚══════════════════════════════════════════════════════╝{NC}")
        
        env = load_env()
        print(f"\n{BOLD}Provedores Disponíveis:{NC}")
        providers = list(PROVIDERS_CONFIG.keys())
        for i, p in enumerate(providers):
            cfg = PROVIDERS_CONFIG[p]
            status = f"{GREEN}[ATIVO]{NC}" if cfg['env_var'] in env or cfg['auth_type'] == "local" else f"{YELLOW}[PENDENTE]{NC}"
            print(f"  {i+1}) {p:15} {status}")
            
        print(f"\n  0) Sair")
        
        choice = input(f"\nSelecione um provedor para configurar (ou 0): ")
        if choice == "0": break
        
        try:
            p_name = providers[int(choice)-1]
            cfg = PROVIDERS_CONFIG[p_name]
            
            print(f"\n--- Configurando {BOLD}{p_name.upper()}{NC} ---")
            if cfg['auth_type'] == "local":
                print(f"Este provedor é local. Certifique-se de que ele está rodando.")
                input("Pressione Enter para marcar como ativo...")
                save_env(cfg['env_var'], "local-active")
            else:
                print(f"Link para Chave: {cfg['doc']}")
                key = input(f"Insira sua API Key para {p_name}: ").strip()
                if key:
                    save_env(cfg['env_var'], key)
                    print(f"{GREEN}✓ Salvo!{NC}")
                    input("\nEnter para continuar...")
        except: pass

if __name__ == "__main__":
    main()
