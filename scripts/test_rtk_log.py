import sys
import os
from pathlib import Path

# Adiciona o plugin ao path
SINAPSE_HOME = os.environ.get("SINAPSE_HOME", str(Path(__file__).resolve().parent.parent))
plugin_path = os.path.join(SINAPSE_HOME, "rtk", "hooks", "hermes", "rtk-rewrite")
sys.path.append(plugin_path)

import __init__ as rtk_plugin

def test_rtk_log():
    print("Simulando execução de 'ls' via RTK...")
    args = {"command": "ls"}
    rtk_plugin._pre_tool_call(tool_name="terminal", args=args)
    
    if args["command"] != "ls":
        print(f"Sucesso: Comando reescrito para '{args['command']}'")
        print("Aguardando 1s para o log assíncrono ser processado...")
        import time
        time.sleep(1)
        
        # Verifica se o log apareceu no banco
        sys.path.append(SINAPSE_HOME)
        from core.database import get_connection
        conn = get_connection()
        row = conn.execute("SELECT * FROM observations WHERE type='execution' ORDER BY created_at DESC LIMIT 1").fetchone()
        conn.close()
        
        if row and "RTK Opt" in row['title']:
            print(f"Sucesso: Log encontrado no UMC: {row['title']}")
            return True
        else:
            print("Erro: Log não encontrado no banco.")
    else:
        print("Aviso: RTK não reescreveu o comando. Verifique se o binário rtk está no PATH e se há regras para 'ls'.")
    return False

if __name__ == "__main__":
    test_rtk_log()
