#!/usr/bin/env python3
"""
Migração/rebuild de embedding: 384d (all-MiniLM-L6-v2) ou 1024d antigo →
1024d (snowflake-arctic-embed2:latest via Ollama).

O que faz:
  1. Dropa search_vec (tabela virtual sqlite-vec com 384d)
  2. Recria com 1024d
  3. Re-indexa todos os neurônios via Ollama snowflake-arctic-embed2:latest
  4. Reseta o índice HNSW (arquivo .bin)

Uso:
  python scripts/setup/migrate_embed_dim.py [--dry-run]
"""
import argparse
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from core.database import DB_PATH, OLLAMA_EMBED_MODEL, get_connection, get_embedder, serialize_f32
from core.indexing import upsert_search_vec

NEW_DIM = 1024


def _exec_with_retry(conn, fn, *, retries: int = 8):
    """Executa escrita SQLite com retry quando o watcher segura lock curto."""
    delay = 0.5
    for attempt in range(retries):
        try:
            return fn()
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt == retries - 1:
                raise
            time.sleep(delay)
            delay = min(delay * 1.5, 5.0)


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
    conn.execute("PRAGMA busy_timeout=30000")

    # Conta neurônios
    total = conn.execute("SELECT COUNT(*) FROM neurons").fetchone()[0]
    print(f"\n[migrate_embed_dim] Neurônios a re-indexar: {total}")
    print(f"[migrate_embed_dim] Backend: EMBED_BACKEND=ollama, modelo={OLLAMA_EMBED_MODEL}, dim={NEW_DIM}")

    if dry_run:
        print("[migrate_embed_dim] DRY-RUN — nenhuma alteração aplicada.")
        conn.close()
        return 0

    # 1. Drop + recreate search_vec
    print("\n[1/3] Recriando search_vec com FLOAT[1024]...")
    def recreate_search_vec():
        conn.execute("DROP TABLE IF EXISTS search_vec")
        conn.execute(f"""
            CREATE VIRTUAL TABLE search_vec USING vec0(
                neuron_id TEXT PRIMARY KEY,
                embedding FLOAT[{NEW_DIM}]
            )
        """)
        conn.commit()

    _exec_with_retry(conn, recreate_search_vec)
    print("  ✓ search_vec recriada")

    # 2. Re-indexar apenas neurônios ainda não indexados
    already = conn.execute("SELECT COUNT(*) FROM search_vec").fetchone()[0]
    print(f"\n[2/3] Re-indexando neurônios via {OLLAMA_EMBED_MODEL} ({already} já indexados)...")
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
    batch_size = 25
    embedder = get_embedder()
    if embedder is None:
        raise RuntimeError("Nenhum backend de embedding disponível.")

    for start in range(0, remaining, batch_size):
        batch = rows[start : start + batch_size]
        ids = [row["id"] for row in batch]
        texts = []
        for row in batch:
            text = str(row["text"] or "").strip()[:5000]
            texts.append(text or row["id"])

        try:
            vectors = [list(vec) for vec in embedder.embed(texts)]
            if len(vectors) != len(batch):
                raise RuntimeError(f"embedding count mismatch: {len(vectors)} != {len(batch)}")
        except Exception as e:
            errors += len(batch)
            print(f"  ⚠ erro no batch {start + 1}-{start + len(batch)}: {e}", flush=True)
            continue

        def write_batch():
            for nid, vec in zip(ids, vectors):
                upsert_search_vec(conn, nid, serialize_f32(vec))
            conn.commit()

        try:
            _exec_with_retry(conn, write_batch)
            indexed += len(batch)
        except Exception as e:
            errors += len(batch)
            print(f"  ⚠ erro ao gravar batch {start + 1}-{start + len(batch)}: {e}", flush=True)
            conn.rollback()

        done = min(start + len(batch), remaining)
        if done % (batch_size * 4) == 0 or done == remaining:
            elapsed = time.time() - t0
            rate = done / elapsed if elapsed else 0
            eta = (remaining - done) / rate if rate > 0 else 0
            print(f"  {done}/{remaining} ({rate:.1f}/s) ETA: {eta:.0f}s", flush=True)

    conn.commit()
    elapsed = time.time() - t0
    print(f"  ✓ {indexed} neurônios indexados em {elapsed:.1f}s ({indexed/elapsed:.1f}/s)")
    if errors:
        print(f"  ⚠ {errors} erros — verifique os neurônios acima")

    # 3. Reset HNSW
    print("\n[3/3] Resetando índice HNSW...")
    _reset_hnsw()

    # 4. Atualiza indexed_at para forçar re-build do HNSW no próximo Dream Cycle
    _exec_with_retry(conn, lambda: (conn.execute("UPDATE neurons SET indexed_at = NULL"), conn.commit()))
    conn.close()

    print(f"\n[migrate_embed_dim] Concluído. {indexed}/{total} re-indexados. "
          f"Erros: {errors}. Tempo total: {elapsed:.1f}s")
    return errors


def main():
    parser = argparse.ArgumentParser(description="Recria search_vec 1024d com o embedder Ollama atual")
    parser.add_argument("--dry-run", action="store_true", help="Apenas informa, não altera")
    args = parser.parse_args()

    errors = migrate(dry_run=args.dry_run)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
