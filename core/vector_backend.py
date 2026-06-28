"""VectorBackend — contrato único de vetores (docs/11 §9, K2).

Local-first: `SQLiteVecBackend` (sqlite-vec sobre `hive_mind.db`) é o default e
sempre funcional. `MilvusBackend` é o backend de produção atrás de
`VECTOR_BACKEND=milvus`. A aplicação nunca chama Milvus fora deste contrato
(não troca a anatomia por infra).

Estado (frente K em andamento): `memory_vectors` é servida por
`hive_mind.db/search_vec`; `observation_vectors` é servida por
`claude-mem.db/vec_observations` em modo read-only local, porque a escrita
canônica continua sendo do `sqlite-vec-worker`. As demais coleções do registro
(`document_vectors`, ...) são `planned` — `upsert/query` levantam
`NotImplementedError` até a fase que as criar/backfilla (K2 task 8, K6...).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Optional, Protocol, runtime_checkable

from core.vector_collections import EMBED_DIM, get_collection


@runtime_checkable
class VectorBackend(Protocol):
    def upsert(self, collection: str, id: str, vector: list[float],
               metadata: Optional[dict] = None) -> None: ...
    def delete(self, collection: str, id: str) -> None: ...
    def query(self, collection: str, vector: list[float], top_k: int = 10,
              filters: Optional[dict] = None) -> list[dict]: ...
    def hybrid_query(self, collection: str, text: str, vector: list[float],
                     filters: Optional[dict] = None, top_k: int = 10) -> list[dict]: ...
    def count(self, collection: str, filters: Optional[dict] = None) -> int: ...
    def health(self) -> dict: ...


class SQLiteVecBackend:
    """Backend local sobre sqlite-vec.

    `memory_vectors` usa `hive_mind.db`; `observation_vectors` usa
    `claude-mem.db`. Passe `conn`/`claude_mem_db` em testes reais; em runtime,
    os caminhos canônicos são resolvidos por `core.database` e `CLAUDE_MEM_DB`.
    """

    def __init__(self, conn=None, claude_mem_db: str | Path | None = None):
        self._conn = conn
        self._claude_mem_db = Path(
            claude_mem_db
            or os.environ.get("CLAUDE_MEM_DB")
            or (Path.home() / ".claude-mem" / "claude-mem.db")
        )
        self._claude_conn = None

    # -- helpers -----------------------------------------------------------
    def _connection(self):
        if self._conn is not None:
            return self._conn
        from core.database import get_connection
        return get_connection()

    def _claude_connection(self):
        if self._claude_conn is not None:
            return self._claude_conn
        if not self._claude_mem_db.exists():
            raise FileNotFoundError(f"claude-mem.db nao encontrado: {self._claude_mem_db}")
        conn = sqlite3.connect(self._claude_mem_db)
        conn.row_factory = sqlite3.Row
        conn.enable_load_extension(True)
        try:
            import sqlite_vec

            sqlite_vec.load(conn)
        finally:
            conn.enable_load_extension(False)
        self._claude_conn = conn
        return conn

    def _served(self, name: str):
        c = get_collection(name)
        if c.status != "live":
            raise NotImplementedError(
                f"coleção {name!r} é 'planned' — sem tabela/backfill ainda (frente K)"
            )
        if c.db not in {"hive_mind", "claude_mem"}:
            raise NotImplementedError(f"coleção {name!r} vive em DB desconhecido: {c.db}")
        return c

    @staticmethod
    def _blob(vector: list[float]):
        from core.database import serialize_f32
        if len(vector) != EMBED_DIM:
            raise ValueError(f"vetor com {len(vector)}d; esperado {EMBED_DIM}d")
        return serialize_f32(vector)

    @staticmethod
    def _json_vector(vector: list[float]) -> str:
        if len(vector) != EMBED_DIM:
            raise ValueError(f"vetor com {len(vector)}d; esperado {EMBED_DIM}d")
        return json.dumps(vector)

    @staticmethod
    def _obs_filter(filters: Optional[dict]) -> tuple[list[str], list[Any], dict[str, Any]]:
        filters = filters or {}
        clauses: list[str] = []
        params: list[Any] = []
        post: dict[str, Any] = {}
        allowed = {"project", "knowledge_type", "type", "workspace_id"}
        for key, value in filters.items():
            if key not in allowed:
                raise ValueError(f"filtro sqlite observation_vectors nao permitido: {key!r}")
            if value is None:
                continue
            if key == "project":
                clauses.append("o.project = ?")
                params.append(str(value))
            elif key in {"knowledge_type", "type"}:
                clauses.append("o.type = ?")
                params.append(str(value))
            elif key == "workspace_id":
                post["workspace_id"] = str(value)
        return clauses, params, post

    @staticmethod
    def _workspace_from_metadata(raw: str | None) -> str:
        if not raw:
            return "default"
        try:
            data = json.loads(raw)
        except Exception:
            return "default"
        return str(data.get("workspace_id") or "default") if isinstance(data, dict) else "default"

    # -- contrato ----------------------------------------------------------
    def upsert(self, collection, id, vector, metadata=None):
        c = self._served(collection)
        if c.db == "claude_mem":
            raise NotImplementedError(
                "observation_vectors e worker-owned: escreva via sqlite-vec-worker/claude-mem"
            )
        conn = self._connection()
        conn.execute(f"DELETE FROM {c.table} WHERE {c.id_col} = ?", (id,))
        conn.execute(
            f"INSERT INTO {c.table}({c.id_col}, embedding) VALUES (?, ?)",
            (id, self._blob(vector)),
        )
        conn.commit()

    def delete(self, collection, id):
        c = self._served(collection)
        if c.db == "claude_mem":
            raise NotImplementedError(
                "observation_vectors e worker-owned: remocao direta pelo VectorBackend local nao e permitida"
            )
        conn = self._connection()
        conn.execute(f"DELETE FROM {c.table} WHERE {c.id_col} = ?", (id,))
        conn.commit()

    def query(self, collection, vector, top_k=10, filters=None):
        c = self._served(collection)
        if c.db == "claude_mem":
            return self._query_observation_vectors(vector, top_k=top_k, filters=filters)
        conn = self._connection()
        # Over-fetch quando há filtro de workspace (filtra após o KNN).
        ws = (filters or {}).get("workspace_id")
        k = top_k * 3 if ws else top_k
        rows = conn.execute(
            f"SELECT {c.id_col} AS id, distance FROM {c.table} "
            f"WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
            (self._blob(vector), k),
        ).fetchall()
        out = [{"id": r["id"], "distance": r["distance"],
                "score": round(1.0 - r["distance"], 4)} for r in rows]
        if ws and c.name == "memory_vectors":
            ids = [r["id"] for r in out]
            if ids:
                ph = ",".join("?" * len(ids))
                allowed = {
                    row[0] for row in conn.execute(
                        f"SELECT id FROM neurons WHERE workspace_id = ? AND id IN ({ph})",
                        (ws, *ids),
                    )
                }
                out = [r for r in out if r["id"] in allowed]
        return out[:top_k]

    def _query_observation_vectors(self, vector, top_k=10, filters=None):
        conn = self._claude_connection()
        clauses, params, post = self._obs_filter(filters)
        where = " AND " + " AND ".join(clauses) if clauses else ""
        overfetch = top_k * 3 if post else top_k
        rows = conn.execute(
            f"""
            SELECT
                v.rowid AS id,
                distance,
                o.project,
                o.type AS knowledge_type,
                o.title,
                o.created_at,
                o.content_hash,
                o.metadata
            FROM vec_observations v
            JOIN observations o ON o.id = v.rowid
            WHERE v.embedding MATCH ?
              AND k = ?
              {where}
            ORDER BY distance
            """,
            (self._json_vector(vector), overfetch, *params),
        ).fetchall()
        out = []
        for row in rows:
            if post.get("workspace_id") and self._workspace_from_metadata(row["metadata"]) != post["workspace_id"]:
                continue
            out.append({
                "id": int(row["id"]),
                "distance": row["distance"],
                "score": round(1.0 - row["distance"], 4),
                "metadata": {
                    "project": row["project"],
                    "knowledge_type": row["knowledge_type"],
                    "title": row["title"] or "",
                    "created_at": row["created_at"] or "",
                    "hash": row["content_hash"] or "",
                    "workspace_id": self._workspace_from_metadata(row["metadata"]),
                },
            })
        return out[:top_k]

    def hybrid_query(self, collection, text, vector, filters=None, top_k=10):
        c = self._served(collection)
        vec_hits = {r["id"]: r["score"] for r in
                    self.query(collection, vector, top_k=top_k, filters=filters)}
        # FTS só faz sentido para memory_vectors (search_fts é keyed por neuron_id).
        if c.name == "memory_vectors" and text.strip():
            conn = self._connection()
            try:
                fts = conn.execute(
                    "SELECT neuron_id AS id FROM search_fts WHERE search_fts MATCH ? LIMIT ?",
                    (text, top_k),
                ).fetchall()
                for r in fts:
                    vec_hits.setdefault(r["id"], 0.0)
            except Exception:
                pass
        merged = [{"id": i, "score": s} for i, s in vec_hits.items()]
        merged.sort(key=lambda r: r["score"], reverse=True)
        return merged[:top_k]

    def count(self, collection, filters=None):
        c = self._served(collection)
        if c.db == "claude_mem":
            conn = self._claude_connection()
            clauses, params, post = self._obs_filter(filters)
            where = " WHERE " + " AND ".join(clauses) if clauses else ""
            rows = conn.execute(
                f"""
                SELECT o.metadata
                FROM vec_observations v
                JOIN observations o ON o.id = v.rowid
                {where}
                """,
                tuple(params),
            ).fetchall()
            if post.get("workspace_id"):
                return sum(
                    1
                    for row in rows
                    if self._workspace_from_metadata(row["metadata"]) == post["workspace_id"]
                )
            return len(rows)
        conn = self._connection()
        return conn.execute(f"SELECT COUNT(*) FROM {c.table}").fetchone()[0]

    def health(self):
        conn = self._connection()
        try:
            n = self.count("memory_vectors")
            health = {"backend": "sqlite_vec", "ok": True, "memory_vectors": n}
            try:
                health["observation_vectors"] = self.count("observation_vectors")
            except Exception as exc:
                health["observation_vectors_error"] = str(exc)
            return health
        except Exception as e:
            return {"backend": "sqlite_vec", "ok": False, "error": str(e)}


class MilvusBackend:
    """Backend de produção atrás de `VECTOR_BACKEND=milvus`.

    Cria coleções Milvus sob demanda com schema explícito e metadados canônicos.
    `collection_prefix` existe para testes reais isolados e ambientes multi-app.
    """

    METADATA_FIELDS = (
        "parent_id",
        "parent_type",
        "brain_lobe",
        "knowledge_type",
        "project",
        "source_uri",
        "hash",
        "valid_at",
        "workspace_id",
    )
    _MAX_LENGTH = {
        "id": 256,
        "parent_id": 256,
        "parent_type": 64,
        "brain_lobe": 64,
        "knowledge_type": 64,
        "project": 256,
        "source_uri": 1024,
        "hash": 128,
        "valid_at": 64,
        "workspace_id": 128,
    }

    def __init__(self, uri: Optional[str] = None, collection_prefix: Optional[str] = None):
        from pymilvus import MilvusClient

        self.uri = uri or os.environ.get("MILVUS_URI", "http://localhost:19530")
        self.collection_prefix = collection_prefix if collection_prefix is not None else os.environ.get("MILVUS_COLLECTION_PREFIX", "hm_")
        self._client = MilvusClient(uri=self.uri)

    @staticmethod
    def _escape(value: str) -> str:
        return str(value).replace("\\", "\\\\").replace('"', '\\"')

    def _collection_name(self, collection: str) -> str:
        get_collection(collection)
        return f"{self.collection_prefix}{collection}"

    def _filter_expr(self, filters: Optional[dict]) -> str:
        if not filters:
            return ""
        parts = []
        allowed = set(self.METADATA_FIELDS) | {"id"}
        for key, value in filters.items():
            if key not in allowed:
                raise ValueError(f"filtro Milvus nao permitido: {key!r}")
            if value is None:
                continue
            parts.append(f'{key} == "{self._escape(str(value))}"')
        return " and ".join(parts)

    def _validate_vector(self, vector: list[float]) -> None:
        if len(vector) != EMBED_DIM:
            raise ValueError(f"vetor com {len(vector)}d; esperado {EMBED_DIM}d")

    def _validate_metadata(self, metadata: Optional[dict]) -> dict[str, str]:
        metadata = metadata or {}
        missing = [field for field in self.METADATA_FIELDS if not metadata.get(field)]
        if missing:
            raise ValueError(f"metadata obrigatorio ausente: {', '.join(missing)}")
        return {field: str(metadata[field]) for field in self.METADATA_FIELDS}

    def _ensure_collection(self, collection: str) -> str:
        name = self._collection_name(collection)
        if self._client.has_collection(name):
            return name

        from pymilvus import DataType, MilvusClient

        schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field("id", DataType.VARCHAR, is_primary=True, max_length=self._MAX_LENGTH["id"])
        schema.add_field("vector", DataType.FLOAT_VECTOR, dim=EMBED_DIM)
        for field in self.METADATA_FIELDS:
            schema.add_field(field, DataType.VARCHAR, max_length=self._MAX_LENGTH[field])

        index_params = self._client.prepare_index_params()
        index_params.add_index("vector", index_type="AUTOINDEX", metric_type="COSINE")
        self._client.create_collection(name, schema=schema, index_params=index_params)
        return name

    def upsert(self, collection, id, vector, metadata=None):
        self._validate_vector(vector)
        meta = self._validate_metadata(metadata)
        name = self._ensure_collection(collection)
        row = {"id": str(id), "vector": vector, **meta}
        self._client.upsert(name, [row])
        self._client.flush(name)
        self._client.load_collection(name)

    def delete(self, collection, id):
        name = self._collection_name(collection)
        if not self._client.has_collection(name):
            return
        self._client.delete(name, ids=[str(id)])
        self._client.flush(name)

    def query(self, collection, vector, top_k=10, filters=None):
        self._validate_vector(vector)
        name = self._collection_name(collection)
        if not self._client.has_collection(name):
            return []
        self._client.load_collection(name)
        rows = self._client.search(
            name,
            data=[vector],
            filter=self._filter_expr(filters),
            limit=top_k,
            output_fields=list(self.METADATA_FIELDS),
        )
        hits = rows[0] if rows else []
        out = []
        for hit in hits:
            entity = dict(hit.get("entity") or {})
            out.append({
                "id": hit.get("id"),
                "distance": hit.get("distance"),
                "score": hit.get("distance"),
                "metadata": {field: entity.get(field) for field in self.METADATA_FIELDS},
            })
        return out

    def hybrid_query(self, collection, text, vector, filters=None, top_k=10):
        # Milvus não é FTS no Hive-Mind; o router compõe FTS/Graph fora daqui.
        return self.query(collection, vector, top_k=top_k, filters=filters)

    def count(self, collection, filters=None):
        name = self._collection_name(collection)
        if not self._client.has_collection(name):
            return 0
        expr = self._filter_expr(filters) or 'id != ""'
        rows = self._client.query(name, filter=expr, output_fields=["id"])
        return len(rows)

    def health(self):
        try:
            collections = self._client.list_collections()
            return {
                "backend": "milvus",
                "ok": True,
                "uri": self.uri,
                "collections": len(collections),
            }
        except Exception as e:
            return {"backend": "milvus", "ok": False, "uri": self.uri, "error": str(e)}


def get_vector_backend(conn=None, claude_mem_db: str | Path | None = None) -> VectorBackend:
    """Factory: `SQLiteVecBackend` (default) ou `MilvusBackend` se
    `VECTOR_BACKEND=milvus`. sqlite-vec continua obrigatório/local-first."""
    if os.environ.get("VECTOR_BACKEND", "sqlite_vec").lower() == "milvus":
        return MilvusBackend()
    return SQLiteVecBackend(conn=conn, claude_mem_db=claude_mem_db)
