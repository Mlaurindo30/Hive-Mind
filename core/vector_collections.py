"""Registro canônico das coleções vetoriais (docs/11 §8) e onde cada uma vive.

B2 (auditoria): as coleções NÃO estão todas no mesmo banco. `observation_vectors`
vive em `claude-mem.db` (processo `sqlite-vec-worker`), não em `hive_mind.db`. O
`VectorBackend` precisa saber disso — "uma interface, várias coleções" não pode
esconder dois bancos. As coleções `hive_mind` vivem em tabelas sqlite-vec
dedicadas e usam `vector_metadata` para proveniência canônica.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Collection:
    name: str
    db: str        # 'hive_mind' | 'claude_mem'
    table: str
    id_col: str
    status: str    # 'live' | 'planned'


# Fonte única do mapeamento coleção→(db, tabela). Ver docs/11 §8.
COLLECTIONS: dict[str, Collection] = {
    "memory_vectors":      Collection("memory_vectors",      "hive_mind", "search_vec",      "neuron_id", "live"),
    "observation_vectors": Collection("observation_vectors", "claude_mem", "vec_observations", "rowid",    "live"),
    "document_vectors":    Collection("document_vectors",    "hive_mind", "vec_documents",   "chunk_id",  "live"),
    "code_vectors":        Collection("code_vectors",        "hive_mind", "vec_code",        "symbol_id", "live"),
    "visual_vectors":      Collection("visual_vectors",      "hive_mind", "vec_visual",      "image_id",  "live"),
    "graph_vectors":       Collection("graph_vectors",       "hive_mind", "vec_graph",       "entity_id", "live"),
    "summary_vectors":     Collection("summary_vectors",     "hive_mind", "vec_summary",     "summary_id","live"),
}

EMBED_DIM = 1024  # snowflake-arctic-embed2:latest


def get_collection(name: str) -> Collection:
    if name not in COLLECTIONS:
        raise KeyError(
            f"coleção desconhecida: {name!r}. Canônicas: {sorted(COLLECTIONS)}"
        )
    return COLLECTIONS[name]
