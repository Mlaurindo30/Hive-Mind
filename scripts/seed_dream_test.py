import sys
import json
from pathlib import Path

# Adiciona o diretório raiz ao path para importar core
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

try:
    from core.database import get_connection, execute_insert
except ImportError:
    print("Erro: core.database não encontrado. Certifique-se de que o script está na pasta correta.")
    sys.exit(1)

def seed_test_data():
    conn = get_connection()
    
    test_obs = [
        ("protocol", "Segurança LLM", "O Conselho exige auditoria 100% real de código. Modelos não devem supor nada sem testar na infraestrutura real."),
        ("architecture", "Hive-Mind Atlas", "A taxonomia do Atlas Infinito é essencial para evitar o silo de informações cronológicas. Cada nó semântico agora mora em sua pasta."),
        ("failure_analysis", "Erro de Polling OpenAI", "Foi determinado que o erro deviceauth_authorization_pending requer um loop contínuo. A implementação atual trata isso com sucesso.")
    ]
    
    for o_type, title, content in test_obs:
        execute_insert(conn, "observations", {
            "type": o_type,
            "title": title,
            "content": content,
            "metadata": json.dumps({"source": "audit-test", "consolidated": False})
        })
        print(f"Semeada observação: {title}")
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    seed_test_data()
