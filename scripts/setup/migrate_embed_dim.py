#!/usr/bin/env python3
"""
Migração de embedding: 384d (all-MiniLM-L6-v2) → 1024d (bge-m3:latest via Ollama).

O que faz:
  1. Dropa search_vec (tabela virtual sqlite-vec com 384d)
  2. Recria com 1024d
  3. Re-indexa todos os neurônios via Ollama bge-m3:latest (~91ms/neuron)
  4. Reseta o índice HNSW (arquivo .bin)

Uso:
  python scripts/setup/migrate_embed_dim.py [--dry-run]
"""
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from core.database import get_connection, DB_PATH, embed_text, serialize_f32
from core.indexing import upsert_search_vec

NEW_DIM = 1024


def _reset_hnsw():
    """Remove o índice HNSW em disco para forçar reconstrução na próxima execução."""
    index_path = Path(DB_PATH).parent / "hnsw_index.bin"
    if index_path.exists():
        index_path.unlink()
        print(f"  ✓ HNSW index removido: {index_path}")
    else:
        print("  ⊘ HNSW index não encontrado (ok)")


def migrate(dry_run: bool = False) -> int:
    conn = get_connection()

    # Conta neurônios
    total = conn.execute("SELECT COUNT(*) FROM neurons").fetchone()[0]
    print(f"\n[migrate_embed_dim] Neurônios a re-indexar: {total}")
    print(f"[migrate_embed_dim] Backend: EMBED_BACKEND=ollama, modelo=bge-m3:latest, dim={NEW_DIM}")

    if dry_run:
        print("[migrate_embed_dim] DRY-RUN — nenhuma alteração aplicada.")
        conn.close()
        return 0

    # 1. Drop + recreate search_vec
    print("\n[1/3] Recriando search_vec com FLOAT[1024]...")
    conn.execute("DROP TABLE IF EXISTS search_vec")
    conn.execute(f"""
        CREATE VIRTUAL TABLE search_vec USING vec0(
            neuron_id TEXT PRIMARY KEY,
            embedding FLOAT[{NEW_DIM}]
        )
    """)
    conn.commit()
    print("  ✓ search_vec recriada")

    # 2. Re-indexar apenas neurônios ainda não indexados
    already = conn.execute("SELECT COUNT(*) FROM search_vec").fetchone()[0]
    print(f"\n[2/3] Re-indexando neurônios via bge-m3 ({already} já indexados)...")
    rows = conn.execute(
        """SELECT n.id, COALESCE(n.content, n.label, '') AS text
           FROM neurons n
           LEFT JOIN search_vec sv ON sv.neuron_id = n.id
           WHERE sv.neuron_id IS NULL
           ORDER BY n.id"""
    ).fetchall()
    remaining = len(rows)
    print(f"  Faltam: {remaining} neurônios")

    if not rows:
        print("  ✓ Todos os neurônios já indexados.")
        _reset_hnsw()
        conn.close()
        return 0

    t0 = time.time()
    indexed = 0
    errors = 0
    batch_size = 50

    for i, row in enumerate(rows):
        nid = row["id"]
        text = str(row["text"] or "").strip()[:5000]
        # Fallback: neurônios sem conteúdo usam o ID como texto representativo
        if not text:
            text = nid
        try:
            vec = embed_text(text)
            if not vec:
                errors += 1
                print(f"  ⚠ vetor vazio para {nid[:12]}: usando ID como fallback")
                vec = embed_text(nid)
            if vec:
                upsert_search_vec(conn, nid, serialize_f32(vec))
                indexed += 1
            else:
                errors += 1
        except Exception as e:
            errors += 1
            print(f"  ⚠ erro no neurônio {nid[:12]}: {e}")

        if (i + 1) % batch_size == 0:
            conn.commit()
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed
            eta = (remaining - i - 1) / rate if rate > 0 else 0
            print(f"  {i+1}/{remaining} ({rate:.1f}/s) ETA: {eta:.0f}s")

    conn.commit()
    elapsed = time.time() - t0
    print(f"  ✓ {indexed} neurônios indexados em {elapsed:.1f}s ({indexed/elapsed:.1f}/s)")
    if errors:
        print(f"  ⚠ {errors} erros — verifique os neurônios acima")

    # 3. Reset HNSW
    print("\n[3/3] Resetando índice HNSW...")
    _reset_hnsw()

    # 4. Atualiza indexed_at para forçar re-build do HNSW no próximo Dream Cycle
    conn.execute("UPDATE neurons SET indexed_at = NULL")
    conn.commit()
    conn.close()

    print(f"\n[migrate_embed_dim] Concluído. {indexed}/{total} re-indexados. "
          f"Erros: {errors}. Tempo total: {elapsed:.1f}s")
    return errors


def main():
    parser = argparse.ArgumentParser(description="Migra search_vec de 384d para 1024d (bge-m3)")
    parser.add_argument("--dry-run", action="store_true", help="Apenas informa, não altera")
    args = parser.parse_args()

    errors = migrate(dry_run=args.dry_run)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
