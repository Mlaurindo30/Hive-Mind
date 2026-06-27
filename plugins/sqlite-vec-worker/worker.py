"""
SQLite-Vec Worker — substituto leve para Chroma no claude-mem.

Usa sqlite-vec (extensão nativa SQLite) + Ollama bge-m3:latest (1024d)
para busca semântica sem dependência de Chroma/uvx/Python MCP.

Backend configurável via EMBED_BACKEND=ollama|fastembed (default: ollama).

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

try:
    import numpy as np
except ImportError:
    np = None

try:
    from fastembed import TextEmbedding
except ImportError:
    TextEmbedding = None

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
# Configurable via env: "ollama" (default, bge-m3 1024d) or "fastembed" (legado, 384d)
EMBED_BACKEND = os.environ.get("EMBED_BACKEND", "ollama")
OLLAMA_BASE = os.environ.get("OLLAMA_BASE", "http://localhost:11434")
OLLAMA_EMBED_MODEL = os.environ.get("OLLAMA_EMBED_MODEL", "bge-m3:latest")
DIMENSIONS = int(os.environ.get("VEC_EMBED_DIM", "1024"))
# Max embeddings to sync at startup before the HTTP server comes up.
# Remaining vectors are synced lazily on each /api/context/semantic request.
STARTUP_SYNC_LIMIT = int(os.environ.get("VEC_STARTUP_SYNC_LIMIT", "500"))
TOP_K = 10


# ---------------------------------------------------------------------------
# Embedding model (lazy load)
# ---------------------------------------------------------------------------

class _OllamaEmbedder:
    """Ollama /api/embeddings — compatible with fastembed's embed() interface."""

    def __init__(self, base_url: str, model: str) -> None:
        self._url = base_url.rstrip("/") + "/api/embeddings"
        self._model = model

    def embed(self, texts):
        if isinstance(texts, str):
            texts = [texts]
        for text in texts:
            import urllib.request
            payload = json.dumps({"model": self._model, "prompt": str(text)[:5000]}).encode()
            req = urllib.request.Request(
                self._url, data=payload, method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read())
            yield data["embedding"]


_embedder = None


def get_embedder():
    global _embedder
    if _embedder is not None:
        return _embedder
    if EMBED_BACKEND == "ollama":
        print(f"[vec-worker] Using Ollama backend ({OLLAMA_EMBED_MODEL})", flush=True)
        _embedder = _OllamaEmbedder(OLLAMA_BASE, OLLAMA_EMBED_MODEL)
        return _embedder
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
    vec = list(get_embedder().embed(text))[0]
    return list(vec)  # handles both numpy arrays (fastembed) and Python lists (ollama)


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


def _vector_count(conn: sqlite3.Connection) -> int:
    """Return current vector count, or zero when the vec table needs creation."""
    try:
        row = conn.execute("SELECT COUNT(*) FROM vec_observations").fetchone()
        return int(row[0])
    except Exception:
        _ensure_schema(conn)
        return 0


def _observation_content(narrative: str | None, text: str | None, facts: str | None) -> str:
    content = narrative or text or ""
    if facts:
        try:
            fact_list = json.loads(facts)
            if isinstance(fact_list, list):
                content += " " + " ".join(str(f) for f in fact_list if f)
        except (json.JSONDecodeError, TypeError):
            pass
    return content.strip()


def _upsert_vec_observation(conn: sqlite3.Connection, row_id: int, vec: list[float]) -> None:
    """Canonical sqlite-vec write path for vec_observations."""
    conn.execute("DELETE FROM vec_observations WHERE rowid = ?", (row_id,))
    conn.execute(
        "INSERT INTO vec_observations(rowid, embedding) VALUES (?, ?)",
        (row_id, json.dumps(vec)),
    )


def sync_vectors(conn: sqlite3.Connection, *, limit: int | None = None) -> int:
    """Make vec_observations match the current observations table.

    The worker is long-lived while claude-mem keeps adding observations. A
    one-time empty-table backfill is not enough; every semantic query must
    reconcile rows that arrived after startup.
    """
    try:
        deleted = conn.execute("""
            DELETE FROM vec_observations
            WHERE rowid NOT IN (SELECT id FROM observations)
        """).rowcount
    except Exception as exc:
        print(f"[vec-worker] WARNING: stale vector cleanup failed: {exc}", flush=True)
        deleted = 0

    rows = conn.execute("""
        SELECT id, narrative, text, facts FROM observations
        WHERE (narrative IS NOT NULL OR text IS NOT NULL)
          AND id NOT IN (SELECT rowid FROM vec_observations)
        ORDER BY id
        """ + (f" LIMIT {int(limit)}" if limit else "")).fetchall()

    count = 0
    for row_id, narrative, text, facts in rows:
        content = _observation_content(narrative, text, facts)
        if not content:
            continue

        try:
            vec = embed(content)
        except Exception as exc:
            print(f"[vec-worker] WARNING: embed failed for observation {row_id}: {exc}", flush=True)
            continue
        try:
            _upsert_vec_observation(conn, row_id, vec)
            count += 1
        except Exception as exc:
            print(f"[vec-worker] WARNING: vector upsert failed for observation {row_id}: {exc}", flush=True)

        if count % 100 == 0:
            print(f"[vec-worker]  ... synced {count} embeddings", flush=True)
            conn.commit()

    conn.commit()
    if count or deleted:
        print(
            f"[vec-worker] Vector sync complete: +{count} embeddings, -{deleted} stale",
            flush=True,
        )
    return count


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

            sync_vectors(db)

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
    synced = sync_vectors(db, limit=STARTUP_SYNC_LIMIT)
    count = _vector_count(db)
    if synced:
        print(f"[vec-worker] vec_observations synced at startup: {count} entries", flush=True)
    else:
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
