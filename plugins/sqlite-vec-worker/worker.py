"""
SQLite-Vec Worker — substituto leve para Chroma no claude-mem.

Usa sqlite-vec (extensão nativa SQLite) + fastembed (all-MiniLM-L6-v2)
para busca semântica sem dependência de Chroma/uvx/Python MCP.

API compatível com /api/context/semantic do claude-mem:
  POST /api/context/semantic
    {"query": "texto da busca"}
    → {"context": "...", "count": N, "items": [...]}
"""

import json
import os
import sqlite3
import sys
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
from fastembed import TextEmbedding

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CLAUDE_MEM_DB = os.environ.get("CLAUDE_MEM_DB")
if not CLAUDE_MEM_DB:
    raise RuntimeError(
        "CLAUDE_MEM_DB is required; refusing to fall back to a global database"
    )
PORT = int(os.environ.get("VEC_WORKER_PORT", "37701"))
MODEL_CACHE_DIR = Path(
    os.environ.get(
        "FASTEMBED_CACHE_PATH",
        str(Path(CLAUDE_MEM_DB).resolve().parent / "models"),
    )
).resolve()
DIMENSIONS = 384  # all-MiniLM-L6-v2
TOP_K = 10

# ---------------------------------------------------------------------------
# Embedding model (lazy load)
# ---------------------------------------------------------------------------

_embedder: TextEmbedding | None = None


def get_embedder() -> TextEmbedding:
    global _embedder
    if _embedder is None:
        MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        print(
            "[vec-worker] Loading embedding model "
            f"(all-MiniLM-L6-v2) from {MODEL_CACHE_DIR}...",
            flush=True,
        )
        _embedder = TextEmbedding(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            cache_dir=str(MODEL_CACHE_DIR),
        )
    return _embedder


def embed(text: str) -> list[float]:
    return list(get_embedder().embed(text))[0].tolist()


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

_db: sqlite3.Connection | None = None


def get_db() -> sqlite3.Connection:
    global _db
    if _db is None:
        if not os.path.isfile(CLAUDE_MEM_DB):
            raise RuntimeError(f"claude-mem DB not found: {CLAUDE_MEM_DB}")
        conn = sqlite3.connect(CLAUDE_MEM_DB)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.enable_load_extension(True)
        try:
            import sqlite_vec

            sqlite_vec.load(conn)
        except Exception as e:
            print(f"[vec-worker] WARNING: sqlite-vec load failed: {e}", flush=True)
        conn.enable_load_extension(False)
        _db = conn
        _ensure_schema(conn)
    return _db


def _ensure_schema(conn: sqlite3.Connection):
    """Create vec0 virtual table if it doesn't exist."""
    try:
        conn.execute(f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS vec_observations
            USING vec0(
                embedding float[{DIMENSIONS}]
                    distance_metric=cosine
            )
        """)
    except Exception as e:
        print(f"[vec-worker] Schema error: {e}", flush=True)


def _needs_backfill(conn: sqlite3.Connection) -> bool:
    """Check if vec0 table is empty (needs backfill from observations)."""
    try:
        row = conn.execute("SELECT COUNT(*) FROM vec_observations").fetchone()
        return row[0] == 0
    except Exception:
        return True


def backfill(conn: sqlite3.Connection):
    """Backfill vec_observations from claude-mem observations table."""
    print(f"[vec-worker] Backfilling embeddings from claude-mem DB...", flush=True)
    rows = conn.execute("""
        SELECT id, narrative, text, facts FROM observations
        WHERE narrative IS NOT NULL OR text IS NOT NULL
        ORDER BY id
    """).fetchall()

    embedder = get_embedder()
    count = 0
    for row_id, narrative, text, facts in rows:
        content = narrative or text or ""
        if facts:
            try:
                fact_list = json.loads(facts)
                if isinstance(fact_list, list):
                    content += " " + " ".join(str(f) for f in fact_list if f)
            except (json.JSONDecodeError, TypeError):
                pass
        if not content.strip():
            continue

        vec = embed(content)
        try:
            conn.execute(
                "INSERT OR REPLACE INTO vec_observations(rowid, embedding) VALUES (?, ?)",
                (row_id, json.dumps(vec)),
            )
            count += 1
        except Exception:
            pass

        if count % 100 == 0:
            print(f"[vec-worker]  ... backfilled {count} embeddings", flush=True)
            conn.commit()

    conn.commit()
    print(f"[vec-worker] Backfill complete: {count} embeddings", flush=True)


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class VecHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._json({"status": "ok", "version": "0.1.0", "db": CLAUDE_MEM_DB})
        else:
            self._json({"error": "not_found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/context/semantic":
            self._handle_semantic()
        else:
            self._json({"error": "not_found"}, 404)

    def _handle_semantic(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            query = body.get("query", "")
        except Exception:
            self._json({"error": "bad_request"}, 400)
            return

        if not query:
            self._json({"error": "query_required"}, 400)
            return

        try:
            db = get_db()

            # Check backfill
            if _needs_backfill(db):
                backfill(db)

            # Embed query
            vec = embed(query)
            vec_json = json.dumps(vec)

            # Search via sqlite-vec
            rows = db.execute(f"""
                SELECT v.rowid, o.narrative, o.text, o.type, o.title, o.created_at, distance
                FROM vec_observations v
                JOIN observations o ON v.rowid = o.id
                WHERE v.embedding MATCH ?
                    AND k = ?
                ORDER BY distance
            """, (vec_json, TOP_K)).fetchall()

            if not rows:
                self._json({"context": "", "count": 0, "items": [], "strategy": "sqlite-vec"})
                return

            # Build context block
            items = []
            contexts = []
            for rowid, narrative, text, otype, title, created_at, distance in rows:
                content = narrative or text or ""
                item = {
                    "id": rowid,
                    "type": otype or "observation",
                    "title": title or "",
                    "content": content[:500],
                    "score": 1.0 - distance,
                    "created_at": created_at or "",
                }
                items.append(item)
                contexts.append(f"[{item['score']:.2f}] {title or otype or 'observation'}: {content[:300]}")

            context = "### sqlite-vec semantic search\n\n" + "\n\n".join(contexts)

            self._json({
                "context": context[:3000],
                "count": len(items),
                "items": items,
                "strategy": "sqlite-vec",
            })

        except Exception as e:
            print(f"[vec-worker] Error: {e}", flush=True)
            self._json({"error": str(e)}, 500)

    def _json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class ThreadedHTTPServer(HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print(f"[vec-worker] Starting on port {PORT}", flush=True)
    print(f"[vec-worker] DB: {CLAUDE_MEM_DB}", flush=True)

    # Pre-load model
    print(f"[vec-worker] Pre-loading embedding model...", flush=True)
    get_embedder()

    # Verify DB
    db = get_db()
    if _needs_backfill(db):
        print(f"[vec-worker] vec_observations empty — will backfill on first query", flush=True)
    else:
        count = db.execute("SELECT COUNT(*) FROM vec_observations").fetchone()[0]
        print(f"[vec-worker] vec_observations: {count} entries", flush=True)

    server = ThreadedHTTPServer(("127.0.0.1", PORT), VecHandler)
    print(f"[vec-worker] Ready on http://127.0.0.1:{PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(f"\n[vec-worker] Shutting down", flush=True)
        server.shutdown()


if __name__ == "__main__":
    main()
