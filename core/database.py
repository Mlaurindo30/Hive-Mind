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
        _embedder = TextEmbedding(model_name="sentence-transformers/all-MiniLM-L6-v2")
    return _embedder

def serialize_f32(vector):
    """Serializa uma lista de floats para o formato f32 do sqlite-vec."""
    return struct.pack(f"{len(vector)}f", *vector)

def generate_uuid():
    """Gera um UUID v4 em formato string."""
    return str(uuid.uuid4())

def get_connection():
    """Retorna uma conexão SQLite com sqlite-vec carregado."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    # Ativa chaves estrangeiras
    conn.execute("PRAGMA foreign_keys = ON;")
    
    if sqlite_vec:
        sqlite_vec.load(conn)
    return conn

def execute_insert(conn, table, data):
    """
    Executa um INSERT injetando um UUID se o campo 'id' estiver ausente.
    'data' deve ser um dicionário com os nomes das colunas e valores.
    Retorna o ID gerado ou utilizado.
    """
    data_copy = dict(data)
    if 'id' not in data_copy or not data_copy['id']:
        data_copy['id'] = generate_uuid()
    
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

def add_observation(title, content, obs_type="event", project=None, session_id=None, neuron_id=None, metadata=None):
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
            "created_at": datetime.now().isoformat()
        }
        obs_id = execute_insert(conn, "observations", data)
        conn.commit()
        return obs_id
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
        print(f"Banco de dados inicializado em: {DB_PATH}")
    except Exception as e:
        print(f"Erro ao inicializar banco: {e}")
    finally:
        conn.close()

def query_hybrid(query_text, limit=10):
    """Realiza busca híbrida (FTS5 + Vetorial) usando RRF (ou combinação simples)."""
    conn = get_connection()
    
    # 1. Busca FTS5 (Texto Exato)
    fts_results = conn.execute("""
        SELECT neuron_id, bm25(search_fts) as score
        FROM search_fts
        WHERE search_fts MATCH ?
        ORDER BY score
        LIMIT ?
    """, (query_text, limit * 2)).fetchall()
    
    # 2. Busca Vetorial (Semântica)
    vec_results = []
    embedder = get_embedder()
    if embedder:
        try:
            query_vec = list(embedder.embed(query_text))[0].tolist()
            serialized = serialize_f32(query_vec)
            
            vec_results = conn.execute("""
                SELECT neuron_id, distance as score
                FROM search_vec
                WHERE embedding MATCH ?
                    AND k = ?
                ORDER BY distance
            """, (serialized, limit * 2)).fetchall()
        except Exception as e:
            print(f"[umc] Erro na busca vetorial: {e}")

    # 3. Combinar resultados (simplificado para MVP)
    # Por enquanto, pegamos os IDs únicos de ambos
    seen_ids = set()
    combined_ids = []
    
    # Prioridade para FTS (exato)
    for row in fts_results:
        if row['neuron_id'] not in seen_ids:
            seen_ids.add(row['neuron_id'])
            combined_ids.append(row['neuron_id'])
            
    # Adiciona hits vetoriais
    for row in vec_results:
        if row['neuron_id'] not in seen_ids:
            seen_ids.add(row['neuron_id'])
            combined_ids.append(row['neuron_id'])

    # 4. Hidratar neurônios
    results = []
    for nid in combined_ids[:limit]:
        neuron = conn.execute("SELECT * FROM neurons WHERE id = ?", (nid,)).fetchone()
        if neuron:
            results.append(dict(neuron))
            
    # 5. Adicionar observações recentes relacionadas (opcional)
    # TODO: Relacionar observações via neuron_id ou busca textual
            
    conn.close()
    return results

if __name__ == "__main__":
    init_db()
