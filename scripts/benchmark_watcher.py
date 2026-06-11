import time
import os
import sqlite3
import uuid
from pathlib import Path

PROJECT_ROOT = "/home/michel/Documentos/Projects/Hive-Mind"
VAULT_DIR = os.path.join(PROJECT_ROOT, "cerebro")
DB_PATH = os.path.join(PROJECT_ROOT, "hive_mind.db")

def benchmark():
    unique_tag = f"BENCH-{uuid.uuid4().hex[:6]}"
    test_file = os.path.join(VAULT_DIR, "BenchMark.md")
    
    print(f"--- Benchmark Hive-Mind Watcher ---")
    print(f"Tag única: {unique_tag}")
    
    # Inicia com arquivo limpo
    if os.path.exists(test_file):
        os.remove(test_file)
    
    with open(test_file, "w") as f:
        f.write(f"# BenchMark\nTeste de performance.\n")
    
    print("Aguardando detecção inicial (5s)...")
    time.sleep(5) 
    
    start_time = time.perf_counter()
    
    # Gatilho: Modifica o arquivo
    print("Modificando arquivo...")
    with open(test_file, "a") as f:
        f.write(f"\nBusca por: {unique_tag}\n")
    
    # Loop de verificação no SQLite
    print("Aguardando sincronização no banco (timeout 30s)...")
    found = False
    attempts = 0
    while time.perf_counter() - start_time < 30: 
        attempts += 1
        try:
            conn = sqlite3.connect(DB_PATH)
            # Busca no conteúdo de todos os neurônios
            cursor = conn.execute("SELECT label FROM neurons WHERE content LIKE ?", (f"%{unique_tag}%",))
            row = cursor.fetchone()
            conn.close()
            if row:
                end_time = time.perf_counter()
                found = True
                break
        except Exception as e:
            pass
        time.sleep(0.5)
        
    if found:
        duration = end_time - start_time
        print(f"✅ SUCESSO! Sincronizado em {duration:.2f} segundos.")
        print(f"Tentativas de polling: {attempts}")
    else:
        print("❌ FALHA: Timeout. Verificando se o neurônio existe mas sem o conteúdo novo...")
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute("SELECT label, content FROM neurons WHERE label LIKE '%BenchMark%'").fetchone()
        if row:
            print(f"Nota '{row[0]}' encontrada, mas conteúdo era: {repr(row[1])}")
        else:
            print("Nota nem sequer foi encontrada no banco.")
        conn.close()
        
if __name__ == "__main__":
    benchmark()
