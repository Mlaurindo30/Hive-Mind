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

_embedder = None

def get_embedder():
    """Retorna o modelo de embedding (lazy load)."""
    global _embedder
    if _embedder is None and TextEmbedding:
        cache_dir = Path(SINAPSE_HOME) / "claude-mem" / "data" / "models"
        cache_dir.mkdir(parents=True, exist_ok=True)
        _embedder = TextEmbedding(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            cache_dir=str(cache_dir),
        )
    return _embedder


def embed_text(text):
    """Gera o vetor canônico 384d usado por sqlite-vec e HNSW."""
    embedder = get_embedder()
    if embedder is None:
        raise RuntimeError("fastembed não está disponível no ambiente do projeto")
    return list(embedder.embed([text[:5000]]))[0].tolist()

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

    # Ativa chaves estrangeiras e tolerância a locks concorrentes
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 5000;")

    if sqlite_vec:
        conn.enable_load_extension(True)
        try:
            sqlite_vec.load(conn)
        finally:
            conn.enable_load_extension(False)
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
        conn.execute(f"ALTER TABLE observations ADD COLUMN source_machine TEXT DEFAULT '{hostname}'")

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

    conn.commit()

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
    embedder = get_embedder()
    if embedder:
        try:
            query_vec = list(embedder.embed(query_text))[0].tolist()
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
