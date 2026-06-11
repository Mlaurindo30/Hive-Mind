import requests
import time
import os

API_URL = "http://127.0.0.1:37702/api/v1"
API_KEY = os.environ.get("HIVE_MIND_API_KEY", "teste123")
HEADERS = {"Authorization": f"Bearer {API_KEY}"}

def test_secret_redaction():
    print("Testando Redação de Segredos...")
    fake_key = "sk-" + "a" * 48
    payload = {
        "title": "Log de Teste",
        "content": f"Minha chave secreta é {fake_key}",
        "kind": "test",
        "agent_id": "security-tester"
    }
    response = requests.post(f"{API_URL}/observations", json=payload, headers=HEADERS)
    data = response.json()
    
    if data.get("status") == "redacted":
        print(f"  [OK] Segredo redigido com sucesso: {data.get('title')}")
    else:
        print(f"  [FAIL] Falha ao redigir segredo. Resposta: {data}")

def test_rate_limiting():
    print("Testando Rate Limiting (Health Check)...")
    for i in range(5):
        resp = requests.get(f"{API_URL}/health")
        if resp.status_code == 429:
            print(f"  [OK] Rate limit atingido na tentativa {i+1}")
            return
    print("  [INFO] Rate limit não atingido (limite alto em dev).")

if __name__ == "__main__":
    # Inicia o servidor temporariamente se necessário ou assume que está rodando
    try:
        test_secret_redaction()
        test_rate_limiting()
    except Exception as e:
        print(f"Erro no teste: {e}")
