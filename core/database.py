import sqlite3
import os
import json
import struct
import uuid
from pathlib import Path
from datetime import datetime

# Tentativa de carregar sqlite-vec
try:
    import sqlite_vec
except ImportError:
    sqlite_vec = None

# Tentativa de carregar fastembed
try:
    from fastembed import TextEmbedding
except ImportError:
    TextEmbedding = None

SINAPSE_HOME = os.environ.get("SINAPSE_HOME", str(Path(__file__).resolve().parent.parent))
DB_PATH = os.path.join(SINAPSE_HOME, "hive_mind.db")
SCHEMA_PATH = os.path.join(SINAPSE_HOME, "core", "umc_schema.sql")

# Backend de embedding: "ollama" (padrão, bge-m3 1024d) ou "fastembed" (legado, MiniLM 384d)
EMBED_BACKEND = os.environ.get("EMBED_BACKEND", "ollama")
OLLAMA_BASE = os.environ.get("OLLAMA_BASE", "http://localhost:11434")
OLLAMA_EMBED_MODEL = os.environ.get("OLLAMA_EMBED_MODEL", "bge-m3:latest")


class OllamaEmbedder:
    """Wraps Ollama /api/embeddings to match the fastembed embed() interface."""

    def __init__(self, base_url: str, model: str) -> None:
        import urllib.request as _ur
        self._url = base_url.rstrip("/") + "/api/embeddings"
        self._model = model
        self._ur = _ur

    def embed(self, texts):
        """Yields embedding vectors; accepts str or list[str]."""
        if isinstance(texts, str):
            texts = [texts]
        for text in texts:
            prompt_text = str(text)[:5000]
            # Ollama /api/embeddings devolve {"embedding": []} (dim-0) para prompt
            # vazio/whitespace-only. Um vetor dim-0 quebra os vector stores
            # (dim mismatch no nano-vectordb do LightRAG / sqlite-vec). Substitui
            # por um placeholder mínimo para garantir vetor de dimensão fixa.
            if not prompt_text.strip():
                prompt_text = " "
            payload = json.dumps({"model": self._model, "prompt": prompt_text}).encode()
            last_exc = None
            emb = None
            for _attempt in range(2):  # 1 retry: tolera 500 transitório do Ollama
                req = self._ur.Request(
                    self._url, data=payload, method="POST",
                    headers={"Content-Type": "application/json"},
                )
                try:
                    with self._ur.urlopen(req, timeout=30) as r:
                        data = json.loads(r.read())
                    emb = data.get("embedding") or None
                    if emb:
                        break
                except Exception as e:
                    last_exc = e
            if not emb:
                raise last_exc or ValueError("Ollama retornou embedding vazio")
            yield emb


_embedder = None


def get_embedder():
    """Retorna o backend de embedding ativo (lazy load)."""
    global _embedder
    if _embedder is None:
        if EMBED_BACKEND == "ollama":
            _embedder = OllamaEmbedder(OLLAMA_BASE, OLLAMA_EMBED_MODEL)
        elif TextEmbedding is not None:
            cache_dir = Path(SINAPSE_HOME) / "claude-mem" / "data" / "models"
            cache_dir.mkdir(parents=True, exist_ok=True)
            _embedder = TextEmbedding(
                model_name="sentence-transformers/all-MiniLM-L6-v2",
                cache_dir=str(cache_dir),
            )
    return _embedder


def embed_text(text: str) -> list:
    """Gera o vetor de embedding via backend ativo (fastembed ou ollama)."""
    embedder = get_embedder()
    if embedder is None:
        raise RuntimeError(
            "Nenhum backend de embedding disponível. "
            "Instale fastembed ou configure EMBED_BACKEND=ollama."
        )
    vec = list(embedder.embed([text[:5000]]))[0]
    return list(vec)  # funciona tanto com numpy arrays (fastembed) quanto lists (ollama)

def serialize_f32(vector):
    """Serializa uma lista de floats para o formato f32 do sqlite-vec."""
    return struct.pack(f"{len(vector)}f", *vector)

def generate_uuid():
    """Gera um UUID v4 em formato string."""
    return str(uuid.uuid4())

def get_connection():
    """Retorna uma conexão SQLite com sqlite-vec carregado."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row

    # Ativa chaves estrangeiras e tolerância a locks concorrentes.
    # F4.0 (resiliência): WAL deixa leitores concorrentes (capture-realtime,
    # graphify-watch, sqlite-vec worker) não bloquearem o writer do dream, e o
    # busy_timeout maior absorve picos de contenção — antes um ciclo de 225s
    # abortava com 'database is locked'. WAL é persistente (setar 1x basta, mas
    # é idempotente). Falha do PRAGMA não é fatal (DB read-only/legado).
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 30000;")
    try:
        conn.execute("PRAGMA journal_mode = WAL;")
    except sqlite3.OperationalError:
        pass

    if sqlite_vec:
        conn.enable_load_extension(True)
        try:
            sqlite_vec.load(conn)
        finally:
            conn.enable_load_extension(False)

    # CR-SQLite (P8 - sync multi-device): opt-in via HIVE_CRDT_SYNC=true.
    # Quando habilitado:
    #   1. Carrega a extensao nativa crsqlite (integrations/crsqlite/<bin>)
    #   2. Tenta CRR-upgrade em cada tabela CRR-elegivel (silencioso se
    #      tabela nao existe - permite uso em DBs de teste com schema minimo)
    #   3. Falhas nao sao fatais - o cerebro segue funcional sem sync
    # Requer que setup_crdt.py tenha migrado o schema para CRR-compat
    # (core/umc_schema_crr.sql). Ver docs/10-implementation-roadmap.md §4 P8.
    if os.environ.get("HIVE_CRDT_SYNC", "").lower() == "true":
        try:
            from integrations.crsqlite.client import enable_crdt
            # enable_crdt ja carrega a extensao internamente (load_crsqlite_extension
            # e sua primeira operacao); nao chamar duas vezes.
            enable_crdt(conn)
        except (RuntimeError, ImportError, sqlite3.OperationalError) as e:
            # Binario ausente, vendor nao carregado, ou schema nao CRR-compat.
            # Log mas nao quebra - sync opt-in.
            import sys
            print(
                f"[hive-mind] CR-SQLite nao inicializado: {type(e).__name__}: {e}. "
                "Sync desabilitado nesta conexao. Rode setup_crdt.py se quiser sync.",
                file=sys.stderr,
            )
    return conn

def execute_insert(conn, table, data):
    """
    Executa um INSERT injetando um UUID se o campo 'id' estiver ausente.
    'data' deve ser um dicionário com os nomes das colunas e valores.
    Retorna o ID gerado ou utilizado.
    """
    # Whitelist de tabelas permitidas para evitar injeção SQL no nome da tabela
    ALLOWED_TABLES = {
        "neurons", "synapses", "observations", "vault", 
        "ambiguities", "visual_memories", "document_memories"
    }
    if table not in ALLOWED_TABLES:
        raise ValueError(f"Tabela não permitida: {table}")

    data_copy = dict(data)
    if 'id' not in data_copy or not data_copy['id']:
        data_copy['id'] = generate_uuid()
    
    # Valida se os nomes das colunas são identificadores válidos para evitar injeção
    for col in data_copy.keys():
        if not col.isidentifier():
            raise ValueError(f"Nome de coluna inválido: {col}")
    
    columns = ', '.join(data_copy.keys())
    placeholders = ', '.join(['?'] * len(data_copy))
    sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
    
    conn.execute(sql, list(data_copy.values()))
    return data_copy['id']

def register_ambiguity(neuron_id, version_a, version_b):
    """
    Registra um conflito P2P entre duas versões de um neurônio.
    'version_a' e 'version_b' devem ser dicionários com: content, hash, metadata.
    Garante uma forma canônica ordenando pelo hash.
    """
    conn = get_connection()
    try:
        # Ordenação Canônica (baseada no hash) para evitar duplicatas espelhadas
        if version_a['hash'] <= version_b['hash']:
            v1, v2 = version_a, version_b
        else:
            v1, v2 = version_b, version_a
            
        data = {
            "neuron_id": neuron_id,
            "source_a_hash": v1['hash'],
            "source_b_hash": v2['hash'],
            "content_a": v1['content'],
            "content_b": v2['content'],
            "metadata_a": json.dumps(v1['metadata']) if v1.get('metadata') else None,
            "metadata_b": json.dumps(v2['metadata']) if v2.get('metadata') else None,
            "status": "pending",
            "detected_at": datetime.now().isoformat()
        }
        
        amb_id = execute_insert(conn, "ambiguities", data)
        conn.commit()
        return amb_id
    except Exception as e:
        print(f"[database] Erro ao registrar ambiguidade: {e}")
        raise
    finally:
        conn.close()

def add_observation(
    title,
    content,
    obs_type="event",
    project=None,
    session_id=None,
    neuron_id=None,
    metadata=None,
    goal_id=None,
    why=None,
    intent_source=None,
):
    """
    Função de conveniência para adicionar uma observação com UUID automático.
    """
    conn = get_connection()
    try:
        data = {
            "title": title,
            "content": content,
            "type": obs_type,
            "project": project,
            "session_id": session_id,
            "neuron_id": neuron_id,
            "metadata": json.dumps(metadata) if metadata else None,
            "archived": 0,
            "created_at": datetime.now().isoformat(),
            "goal_id": goal_id,
            "why": why,
            "intent_source": intent_source,
        }
        obs_id = execute_insert(conn, "observations", data)
        conn.commit()
        return obs_id
    finally:
        conn.close()

def add_visual_memory(image_path, description=None, ocr_text=None, neuron_id=None, metadata=None):
    """
    Função de conveniência para adicionar uma memória visual com UUID automático.
    """
    conn = get_connection()
    try:
        data = {
            "image_path": image_path,
            "description": description,
            "ocr_text": ocr_text,
            "neuron_id": neuron_id,
            "metadata": json.dumps(metadata) if metadata else None,
            "created_at": datetime.now().isoformat()
        }
        vm_id = execute_insert(conn, "visual_memories", data)
        conn.commit()
        return vm_id
    finally:
        conn.close()

def ensure_migrations(conn):
    """
    Aplica migrações idempotentes em bancos existentes:
    - Coluna 'archived' na tabela observations (0=pendente, 1=consolidado, 2=quarentena)
    - Índice idx_observations_archived
    - Índice composto idx_observations_archived_project (plumbing do dream_cycle)
    - Backfill do formato legado ("archived": true no metadata)
    - Colunas 'uuid' e 'source_machine' (Phase 8: P2P/Syncthing sync)
    """
    try:
        conn.execute("ALTER TABLE observations ADD COLUMN archived INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # Coluna já existe
    conn.execute("CREATE INDEX IF NOT EXISTS idx_observations_archived ON observations(archived)")
    # Phase HM: project plumbing — segregação do dream_cycle por projeto.
    # Envelopado em try/except porque bancos muito legados (sem coluna `project`)
    # ainda existem e `ensure_migrations` deve ser idempotente.
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_observations_archived_project ON observations(archived, project)")
    except sqlite3.OperationalError:
        # Coluna `project` ausente (banco pré-anatômico) — índice será
        # criado na próxima migração quando a coluna for adicionada.
        pass
    # Backfill único: migra observações arquivadas via metadata (legado) para a coluna
    conn.execute("""UPDATE observations SET archived = 1 WHERE metadata LIKE '%"archived": true%' AND archived = 0""")

    # Phase 8: P2P/Syncthing sync columns
    existing_cols = [r[1] for r in conn.execute("PRAGMA table_info(observations)")]
    if "uuid" not in existing_cols:
        conn.execute("ALTER TABLE observations ADD COLUMN uuid TEXT")
    if "source_machine" not in existing_cols:
        import socket
        hostname = socket.gethostname()
        # ALTER nao aceita placeholder no DEFAULT; cria a coluna sem default e
        # popula via UPDATE parametrizado (hostname pode conter aspas/';' — POSIX).
        conn.execute("ALTER TABLE observations ADD COLUMN source_machine TEXT")
        conn.execute(
            "UPDATE observations SET source_machine = ? WHERE source_machine IS NULL",
            (hostname,),
        )

    # Phase HM-11: Intent Memory columns
    if "goal_id" not in existing_cols:
        conn.execute("ALTER TABLE observations ADD COLUMN goal_id TEXT")
    if "why" not in existing_cols:
        conn.execute("ALTER TABLE observations ADD COLUMN why TEXT")
    if "intent_source" not in existing_cols:
        conn.execute("ALTER TABLE observations ADD COLUMN intent_source TEXT")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS goals (
            id TEXT PRIMARY KEY,
            description TEXT NOT NULL,
            steps_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Phase HM-11: Causal graph table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS causal_edges (
            id TEXT PRIMARY KEY,
            cause_neuron_id TEXT NOT NULL,
            effect_neuron_id TEXT NOT NULL,
            label TEXT,
            confidence REAL DEFAULT 1.0,
            source TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_causal_cause ON causal_edges(cause_neuron_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_causal_effect ON causal_edges(effect_neuron_id)")

    # Phase B4: HNSW indexed_at tracking
    neuron_cols = {r[1] for r in conn.execute("PRAGMA table_info(neurons)").fetchall()}
    if neuron_cols and "indexed_at" not in neuron_cols:
        conn.execute("ALTER TABLE neurons ADD COLUMN indexed_at TIMESTAMP")

    # Phase HM-12: Federated Swarm — selective sharing
    if neuron_cols and "visibility" not in neuron_cols:
        conn.execute("ALTER TABLE neurons ADD COLUMN visibility TEXT DEFAULT 'private'")

    # Phase HM-12: Router Sliding Window topic tracking
    if neuron_cols and "topic" not in neuron_cols:
        conn.execute("ALTER TABLE neurons ADD COLUMN topic TEXT")

    # Índice exige a tabela neurons E a coluna updated_at. `topic` é garantido
    # pelo ALTER acima; updated_at precisa pré-existir (tabelas mínimas/legadas
    # podem não ter). Sem este guard duplo, ensure_migrations quebra.
    if neuron_cols and "updated_at" in neuron_cols:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_neurons_topic_updated ON neurons(topic, updated_at)")

    # Memória Viva M9 (doc 08, §14.4-P2): telemetria de sobrevivência do dream cycle.
    # 1 linha por ciclo — permite medir duração e o motivo de término (ok /
    # BUDGET_EXHAUSTED / error) antes de confiar no go-live do sinapse-dream.timer.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dream_cycle_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at DATETIME NOT NULL,
            ended_at DATETIME,
            duration_s REAL,
            observations_processed INTEGER DEFAULT 0,
            ambiguities_processed INTEGER DEFAULT 0,
            ended_reason TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dream_cycle_started ON dream_cycle_log(started_at)")

    conn.commit()

def get_recent_topics(limit=20) -> list[str]:
    """Obtém os tópicos mais recentes da tabela neurons (sliding window)."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT topic 
            FROM neurons 
            WHERE topic IS NOT NULL 
            GROUP BY topic 
            ORDER BY MAX(updated_at) DESC 
            LIMIT ?
        """, (limit,)).fetchall()
        return [row['topic'] for row in rows]
    finally:
        conn.close()

def init_db():
    """Inicializa o banco de dados com o esquema unificado."""
    conn = get_connection()
    with open(SCHEMA_PATH, "r") as f:
        schema = f.read()

    try:
        conn.executescript(schema)
        conn.commit()
        ensure_migrations(conn)
        print(f"Banco de dados inicializado em: {DB_PATH}")
    except Exception as e:
        print(f"Erro ao inicializar banco: {e}")
    finally:
        conn.close()

def _reciprocal_rank_fusion(ranked_lists: list, k: int = 60) -> list:
    """
    Reciprocal Rank Fusion (Cormack et al. 2009).

    ranked_lists: list of ordered lists of neuron_id strings.
    Returns a list of neuron_ids sorted by descending RRF score.
    k=60 is the standard value from the literature.
    """
    from collections import defaultdict
    scores: dict = defaultdict(float)
    for ranked in ranked_lists:
        for rank, item_id in enumerate(ranked, start=1):
            scores[item_id] += 1.0 / (k + rank)
    return sorted(scores.keys(), key=lambda x: scores[x], reverse=True)


def get_causal_neighbors(conn, neuron_id: str, hops: int = 2) -> list[dict]:
    """Return up to `hops`-hop causal neighbors of a neuron (BFS over causal_edges)."""
    visited = {neuron_id}
    frontier = [neuron_id]
    results = []
    for _ in range(hops):
        if not frontier:
            break
        placeholders = ",".join("?" * len(frontier))
        rows = conn.execute(
            f"SELECT effect_neuron_id, label, confidence FROM causal_edges WHERE cause_neuron_id IN ({placeholders})",
            frontier,
        ).fetchall()
        new_frontier = []
        for row in rows:
            eid = row[0] if isinstance(row, (list, tuple)) else row["effect_neuron_id"]
            if eid not in visited:
                visited.add(eid)
                new_frontier.append(eid)
                results.append({
                    "neuron_id": eid,
                    "label": row[1] if isinstance(row, (list, tuple)) else row["label"],
                    "confidence": row[2] if isinstance(row, (list, tuple)) else row["confidence"],
                })
        frontier = new_frontier
    return results


def query_hybrid(query_text, limit=10):
    """Realiza busca hibrida (FTS5 + Vetorial) com Reciprocal Rank Fusion."""
    conn = get_connection()

    # 1. Busca FTS5 (Texto Exato) — lista ordenada de IDs
    try:
        fts_rows = conn.execute("""
            SELECT neuron_id, bm25(search_fts) as score
            FROM search_fts
            WHERE search_fts MATCH ?
            ORDER BY score
            LIMIT ?
        """, (query_text, limit * 2)).fetchall()
        fts_ids = [row['neuron_id'] for row in fts_rows]
    except Exception as e:
        print(f"[umc] Erro na busca FTS5: {e}")
        fts_ids = []

    # 2. Busca Vetorial (Semantica) — lista ordenada de IDs
    vec_ids = []
    try:
        query_vec = embed_text(query_text)
        serialized = serialize_f32(query_vec)
        vec_rows = conn.execute("""
            SELECT neuron_id, distance as score
            FROM search_vec
            WHERE embedding MATCH ?
                AND k = ?
            ORDER BY distance
        """, (serialized, limit * 2)).fetchall()
        vec_ids = [row['neuron_id'] for row in vec_rows]
    except Exception as e:
        print(f"[umc] Erro na busca vetorial: {e}")

    # 3. Combinar com RRF — produz ranking global unico
    ranked_lists = [lst for lst in [fts_ids, vec_ids] if lst]
    if ranked_lists:
        combined_ids = _reciprocal_rank_fusion(ranked_lists)
    else:
        combined_ids = []

    # 4. Hidratar neuronios (um unico SELECT ... IN, preservando a ordem RRF)
    results = []
    top_ids = combined_ids[:limit]
    if top_ids:
        placeholders = ', '.join(['?'] * len(top_ids))
        rows = conn.execute(
            f"SELECT * FROM neurons WHERE id IN ({placeholders})", top_ids
        ).fetchall()
        rows_by_id = {row['id']: dict(row) for row in rows}
        for nid in top_ids:
            neuron = rows_by_id.get(nid)
            if neuron:
                results.append(neuron)

    conn.close()
    return results

if __name__ == "__main__":
    init_db()
