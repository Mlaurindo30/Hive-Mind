#!/usr/bin/env python3
import os
import sys
import struct
import secrets
from pathlib import Path

# Adiciona o diretório raiz ao sys.path para importar o core
sys.path.append(str(Path(__file__).resolve().parent.parent))

from core.database import init_db, get_connection

def serialize_f32(vector):
    """Serializa uma lista de floats para o formato f32 do sqlite-vec."""
    return struct.pack(f"{len(vector)}f", *vector)

def install_dependencies():
    """Fail if uv did not provision the required project-local dependencies."""
    print("Verificando dependências...")
    try:
        import sqlite_vec
        import cryptography
        import dotenv
        print("Dependências principais já instaladas.")
    except ImportError as exc:
        raise RuntimeError(
            "Dependência ausente no .venv. Execute: uv sync --frozen --all-groups"
        ) from exc

def setup_security():
    """Gera e salva HIVE_MIND_API_KEY e HIVE_MIND_MASTER_KEY se não existirem."""
    print("Configurando segurança...")
    env_path = Path(__file__).resolve().parent.parent / ".env"
    
    existing_content = ""
    if env_path.exists():
        with open(env_path, "r") as f:
            existing_content = f.read()

    with open(env_path, "a") as f:
        if "HIVE_MIND_API_KEY" not in existing_content:
            new_api_key = secrets.token_hex(32)
            f.write(f"\nHIVE_MIND_API_KEY={new_api_key}\n")
            print(f"Nova HIVE_MIND_API_KEY gerada.")
        
        if "HIVE_MIND_MASTER_KEY" not in existing_content:
            from cryptography.fernet import Fernet
            new_master_key = Fernet.generate_key().decode()
            f.write(f"HIVE_MIND_MASTER_KEY={new_master_key}\n")
            print(f"Nova HIVE_MIND_MASTER_KEY (Vault) gerada.")

def verify_setup():
    """Verifica se o banco e a extensão vetorial estão funcionando."""
    print("Verificando setup...")
    try:
        conn = get_connection()
        cursor = conn.execute("select vec_version();")
        version = cursor.fetchone()[0]
        print(f"sqlite-vec versão: {version}")
        
        # Teste isolado: nunca toca na tabela search_vec operacional.
        test_vector = [0.1] * 384
        serialized = serialize_f32(test_vector)
        conn.execute(
            "CREATE VIRTUAL TABLE temp.vec_setup_probe USING vec0("
            "id TEXT PRIMARY KEY, embedding FLOAT[384])"
        )
        conn.execute(
            "insert into temp.vec_setup_probe(id, embedding) values (?, ?)",
            ("test-1", serialized)
        )
        cursor = conn.execute(
            "select id from temp.vec_setup_probe where embedding match ? and k = 1",
            (serialized,)
        )
        result = cursor.fetchone()
        if result and result[0] == "test-1":
            print("Busca vetorial validada com sucesso!")
        else:
            print("Falha na validação da busca vetorial.")
        conn.execute("DROP TABLE temp.vec_setup_probe")
        conn.close()
    except Exception as e:
        print(f"Erro na verificação: {e}")
        return False
    return True

def main():
    print("=== Hive-Mind: Setup UMC ===")
    install_dependencies()
    setup_security()
    init_db()
    if verify_setup():
        print("Setup do Unified Memory Core concluído com sucesso!")
    else:
        print("Setup concluído com alertas (verifique logs).")

if __name__ == "__main__":
    main()
