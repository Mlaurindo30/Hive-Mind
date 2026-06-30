import sqlite3
import os
import json
import struct
import uuid
import sys
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

# Backend de embedding: "ollama" (padrao, snowflake-arctic-embed2 1024d) ou
# "fastembed" (legado, MiniLM 384d)
EMBED_BACKEND = os.environ.get("EMBED_BACKEND", "ollama")
OLLAMA_BASE = os.environ.get("OLLAMA_BASE", "http://localhost:11434")
# Decisao 2026-06-27: snowflake-arctic-embed2 substitui bge-m3 como default
# global de embeddings. Mantem 1024d, e nos testes locais teve 0 NaNs nos
# triggers problemáticos e melhor separacao PT/EN vs. conteudo nao relacionado.
OLLAMA_EMBED_MODEL = os.environ.get("OLLAMA_EMBED_MODEL", "snowflake-arctic-embed2:latest")


class OllamaEmbedder:
    """Wraps Ollama /api/embed (batch, L2-normalized) to match the fastembed embed() interface.

    Endpoint moderno /api/embed (campo `input`, resposta `embeddings`), batch-capable.
    Retry com backoff p/ 500 transitório; em batch, isola item-a-item se algo falhar.
    Se um texto falhar de forma persistente, levanta erro claro (visível) em vez de
    mascarar o problema com vetor zero ou troca silenciosa de modelo.
    """

    def __init__(self, base_url: str, model: str) -> None:
        import urllib.request as _ur
        self._url = base_url.rstrip("/") + "/api/embed"
        self._model = model
        self._ur = _ur

    def _post(self, inputs):
        """POST /api/embed com retry+backoff. Retorna list[list[float]] ou None."""
        import time
        payload = json.dumps({"model": self._model, "input": inputs}).encode()
        for attempt in range(3):  # tolera 500 transitório
            req = self._ur.Request(
                self._url, data=payload, method="POST",
                headers={"Content-Type": "application/json"},
            )
            try:
                with self._ur.urlopen(req, timeout=60) as r:
                    data = json.loads(r.read())
                embs = data.get("embeddings")
                if embs:
                    return embs
            except Exception:  # noqa — retry no backoff abaixo
                pass
            time.sleep(0.4 * (attempt + 1))  # backoff: 0.4s, 0.8s, 1.2s
        return None

    @staticmethod
    def _finite(vec) -> bool:
        """Vetor não-vazio e sem NaN/Inf (NaN != NaN; Inf cai no teste de range)."""
        return bool(vec) and all((v == v) and (-1e30 < v < 1e30) for v in vec)

    def embed(self, texts):
        """Yields embedding vectors; accepts str or list[str]."""
        if isinstance(texts, str):
            texts = [texts]
        # Guarda vazio/whitespace: alguns modelos devolvem dim-0 → quebra os vector stores.
        cleaned = [(str(t)[:5000] if str(t)[:5000].strip() else " ") for t in texts]

        embs = self._post(cleaned)  # tenta o batch inteiro primeiro (rápido)
        if embs and len(embs) == len(cleaned) and all(self._finite(v) for v in embs):
            yield from embs
            return

        # Batch falhou: reprocessa item-a-item p/ isolar o problemático.
        for text in cleaned:
            one = self._post([text])
            if one and self._finite(one[0]):
                yield one[0]
            else:
                raise ValueError(
                    f"Ollama embedding falhou/NaN (modelo {self._model}) para input: {text[:80]!r}"
                )


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
        "ambiguities", "visual_memories", "document_memories",
        "knowledge_tombstones", "query_route_log",
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

# ===== B1: Migração CRR-safe (workspace_id + federação + embedding-provenance) =====
# Tabelas que recebem workspace_id (docs/11 §18.1) = CRDT_TABLES + goals.
_WORKSPACE_TABLES = [
    "neurons", "observations", "synapses", "goals", "document_memories",
    "visual_memories", "ambiguities", "causal_edges", "vault",
]


def _table_exists(conn, table) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _table_is_crr(conn, table) -> bool:
    """True se a tabela foi convertida com crsql_as_crr (shadow clock existe)."""
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (f"{table}__crsql_clock",),
    ).fetchone() is not None


def _has_column(conn, table, col) -> bool:
    return any(r[1] == col for r in conn.execute(f"PRAGMA table_info({table})"))


def alter_table_crr_safe(conn, table: str, coldef: str) -> None:
    """ADD COLUMN respeitando CR-SQLite (B1).

    Em tabela CRR, `ALTER` puro quebra a replicação — precisa ser envolvido em
    `crsql_begin_alter`/`crsql_commit_alter`. Em tabela normal, ALTER direto.
    Idempotência é responsabilidade do caller (checar a coluna antes). Colunas
    CRR exigem DEFAULT (P8.3): passe sempre `... DEFAULT <x>`.
    """
    sql = f"ALTER TABLE {table} ADD COLUMN {coldef}"
    if _table_is_crr(conn, table):
        conn.execute("SELECT crsql_begin_alter(?)", (table,))
        try:
            conn.execute(sql)
        finally:
            conn.execute("SELECT crsql_commit_alter(?)", (table,))
    else:
        conn.execute(sql)


def add_column_if_missing(conn, table: str, coldef: str) -> bool:
    """Adiciona coluna de forma idempotente e CRR-safe.

    Retorna True quando a coluna foi adicionada nesta chamada.
    """
    if not _table_exists(conn, table):
        return False
    col = coldef.split()[0]
    if _has_column(conn, table, col):
        return False
    alter_table_crr_safe(conn, table, coldef)
    return True


def _db_file_of(conn) -> str:
    """Caminho do arquivo do banco 'main' (vazio para :memory:/temp)."""
    row = conn.execute("PRAGMA database_list").fetchone()
    return row[2] if row and row[2] else ""


def _backup_db_once(conn, suffix: str) -> None:
    """B8: backup consistente (API `backup()`) antes de migração irreversível.

    Roda só 1x (se o `.<suffix>` ainda não existe) e só para DB em arquivo real
    (pula `:memory:`/temp). `crsql_as_crr` é irreversível — este é o ponto de
    retorno.
    """
    db_file = _db_file_of(conn)
    if not db_file:
        return
    bak = f"{db_file}.{suffix}"
    if os.path.exists(bak):
        return
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except sqlite3.OperationalError:
        pass
    bak_conn = sqlite3.connect(bak)
    try:
        conn.backup(bak_conn)
    finally:
        bak_conn.close()
    import sys
    print(f"[hive-mind] backup pré-migração: {bak}", file=sys.stderr)


def migrate_workspace_and_federation(conn) -> None:
    """B1/B6: `workspace_id` nas 9 tabelas + federação/embedding-provenance em
    `neurons`. CRR-safe e idempotente. Single-user fica com `workspace_id='default'`.
    """
    # B8: backup antes da 1ª aplicação real (quando ha coluna a adicionar).
    if _table_exists(conn, "neurons") and not _has_column(conn, "neurons", "workspace_id"):
        _backup_db_once(conn, "pre-workspace")

    for table in _WORKSPACE_TABLES:
        if not _table_exists(conn, table):
            continue
        if not _has_column(conn, table, "workspace_id"):
            alter_table_crr_safe(conn, table, "workspace_id TEXT NOT NULL DEFAULT 'default'")
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{table}_workspace ON {table}(workspace_id)"
        )
    # Federação (docs/11 §18.3) + proveniência de embedding (§18.4) — em neurons.
    if _table_exists(conn, "neurons"):
        for coldef in (
            "origin_instance TEXT DEFAULT NULL",
            "origin_signature TEXT DEFAULT NULL",
            "embedding_model TEXT DEFAULT NULL",
            "embedding_dim INTEGER DEFAULT NULL",
        ):
            if not _has_column(conn, "neurons", coldef.split()[0]):
                alter_table_crr_safe(conn, "neurons", coldef)


def allow_deferred_migrations() -> bool:
    """Escape hatch explícito para abrir banco legado com migração quebrada.

    Migração estrutural da Frente K falha fechado por padrão. Se isso quebrar,
    o correto é consertar a migração. Este bypass existe só para diagnóstico de
    banco legado e deve deixar log visível.
    """
    value = os.environ.get("HIVE_ALLOW_DEFERRED_MIGRATIONS", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def ensure_migrations(conn):
    """
    Aplica migrações idempotentes em bancos existentes:
    - Coluna 'archived' na tabela observations (0=pendente, 1=consolidado, 2=quarentena)
    - Índice idx_observations_archived
    - Índice composto idx_observations_archived_project (plumbing do dream_cycle)
    - Backfill do formato legado ("archived": true no metadata)
    - Colunas 'uuid' e 'source_machine' (Phase 8: P2P/Syncthing sync)
    """
    add_column_if_missing(conn, "observations", "archived INTEGER DEFAULT 0")
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
    add_column_if_missing(conn, "observations", "uuid TEXT DEFAULT NULL")
    if add_column_if_missing(conn, "observations", "source_machine TEXT DEFAULT NULL"):
        import socket
        hostname = socket.gethostname()
        # ALTER nao aceita placeholder no DEFAULT; cria a coluna sem default e
        # popula via UPDATE parametrizado (hostname pode conter aspas/';' — POSIX).
        conn.execute(
            "UPDATE observations SET source_machine = ? WHERE source_machine IS NULL",
            (hostname,),
        )

    # Phase HM-11: Intent Memory columns
    add_column_if_missing(conn, "observations", "goal_id TEXT DEFAULT NULL")
    add_column_if_missing(conn, "observations", "why TEXT DEFAULT NULL")
    add_column_if_missing(conn, "observations", "intent_source TEXT DEFAULT NULL")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS goals (
            id TEXT PRIMARY KEY,
            description TEXT NOT NULL,
            steps_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            workspace_id TEXT NOT NULL DEFAULT 'default'
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
    if neuron_cols:
        add_column_if_missing(conn, "neurons", "indexed_at TIMESTAMP DEFAULT NULL")

    # Phase HM-12: Federated Swarm — selective sharing
    if neuron_cols:
        add_column_if_missing(conn, "neurons", "visibility TEXT DEFAULT 'private'")

    # Phase HM-12: Router Sliding Window topic tracking
    if neuron_cols:
        add_column_if_missing(conn, "neurons", "topic TEXT DEFAULT NULL")

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

    # K2: coleções vetoriais auxiliares. search_vec cobre memória principal; as
    # demais coleções precisam de tabelas próprias + metadados canônicos para
    # sync local -> Milvus sem perder proveniência.
    try:
        conn.execute("SELECT vec_version()").fetchone()
        sqlite_vec_loaded = True
    except sqlite3.OperationalError:
        sqlite_vec_loaded = False
    if sqlite_vec_loaded:
        for table, id_col in (
            ("vec_documents", "chunk_id"),
            ("vec_code", "symbol_id"),
            ("vec_visual", "image_id"),
            ("vec_graph", "entity_id"),
            ("vec_summary", "summary_id"),
        ):
            conn.execute(
                f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS {table} USING vec0(
                    {id_col} TEXT PRIMARY KEY,
                    embedding FLOAT[1024]
                )
                """
            )
    conn.execute("""
        CREATE TABLE IF NOT EXISTS vector_metadata (
            collection TEXT NOT NULL,
            id TEXT NOT NULL,
            parent_id TEXT NOT NULL,
            parent_type TEXT NOT NULL,
            brain_lobe TEXT NOT NULL,
            knowledge_type TEXT NOT NULL,
            project TEXT NOT NULL DEFAULT 'default',
            source_uri TEXT NOT NULL,
            hash TEXT NOT NULL,
            valid_at TEXT NOT NULL,
            workspace_id TEXT NOT NULL DEFAULT 'default',
            PRIMARY KEY(collection, id)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_vector_metadata_collection_workspace
        ON vector_metadata(collection, workspace_id)
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS document_chunks (
            id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL,
            parent_id TEXT NOT NULL,
            parent_type TEXT NOT NULL DEFAULT 'document',
            source_uri TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            heading TEXT,
            content TEXT NOT NULL,
            offset_start INTEGER NOT NULL,
            offset_end INTEGER NOT NULL,
            hash TEXT NOT NULL,
            metadata JSON,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            workspace_id TEXT NOT NULL DEFAULT 'default',
            FOREIGN KEY(document_id) REFERENCES document_memories(id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_document_chunks_document
        ON document_chunks(document_id, chunk_index)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_document_chunks_source
        ON document_chunks(source_uri, offset_start, offset_end)
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_candidates (
            id TEXT PRIMARY KEY,
            source_type TEXT NOT NULL,
            source_id TEXT NOT NULL,
            knowledge_type TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            project TEXT NOT NULL DEFAULT 'default',
            workspace_id TEXT NOT NULL DEFAULT 'default',
            evidence_json TEXT NOT NULL,
            metadata_json TEXT,
            hash TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'candidate',
            neuron_id TEXT,
            error TEXT,
            retry_policy TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            promoted_at TEXT,
            UNIQUE(source_id, knowledge_type, hash, workspace_id)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_knowledge_candidates_source
        ON knowledge_candidates(source_type, source_id, status)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_knowledge_candidates_type_workspace
        ON knowledge_candidates(knowledge_type, workspace_id, status)
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_tombstones (
            id TEXT PRIMARY KEY,
            target_type TEXT NOT NULL,
            target_id TEXT NOT NULL,
            collection TEXT,
            reason TEXT NOT NULL,
            actor TEXT NOT NULL DEFAULT 'system',
            metadata_json TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            workspace_id TEXT NOT NULL DEFAULT 'default'
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_knowledge_tombstones_target
        ON knowledge_tombstones(target_type, target_id, collection, workspace_id)
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS query_route_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query_hash TEXT NOT NULL,
            intent TEXT NOT NULL,
            first_route TEXT,
            retrieval_path_json TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            workspace_id TEXT NOT NULL DEFAULT 'default'
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_query_route_log_created
        ON query_route_log(created_at, workspace_id)
    """)

    # B1/B6 (frente K, K0): workspace_id + federação + embedding-provenance.
    # CRR-safe e idempotente. Falha fechado por padrão: schema parcial não é
    # modo operacional; o bypass explícito abaixo é só para diagnóstico legado.
    try:
        migrate_workspace_and_federation(conn)
    except sqlite3.OperationalError as e:
        import sys
        if allow_deferred_migrations():
            print(
                "[hive-mind] migrate_workspace_and_federation adiada por "
                f"HIVE_ALLOW_DEFERRED_MIGRATIONS=1: {e}",
                file=sys.stderr,
            )
        else:
            raise RuntimeError(
                "migrate_workspace_and_federation falhou; corrija a migração "
                "workspace/federação em vez de seguir com schema parcial. "
                "Para diagnóstico de DB legado, use "
                "HIVE_ALLOW_DEFERRED_MIGRATIONS=1."
            ) from e

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
        print(f"[umc] Erro na busca FTS5: {e}", file=sys.stderr)
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
        print(f"[umc] Erro na busca vetorial: {e}", file=sys.stderr)

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
