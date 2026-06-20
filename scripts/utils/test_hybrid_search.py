#!/usr/bin/env python3
import sys
import os
from pathlib import Path

# Adiciona o diretório raiz ao sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from core.database import query_hybrid

def test_search(query):
    print(f"=== Buscando por: '{query}' ===")
    results = query_hybrid(query)
    print(f"Encontrados {len(results)} resultados.")
    for i, r in enumerate(results):
        print(f"{i+1}. [{r['type']}] {r['label']} (ID: {r['id']})")
        # print(f"   Contexto: {r['content'][:100]}...")
    print("-" * 30)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        test_search(sys.argv[1])
    else:
        # Queries de teste
        test_search("sinapse")
        test_search("neural memory")
        test_search("backend")
