"""CR-SQLite client - wrapper Python sobre o binario nativo crsqlite.

Carrega a extensao nativa (crsqlite.so/.dylib/.dll) e expoe primitivas para
sincronizacao CRDT do hive_mind.db. NAO usar `import crsqlite` - nao
existe wheel PyPI; o binario vem do install.sh e fica em
integrations/crsqlite/crsqlite.{so,dylib,dll}.

Fluxo correto:
    conn = sqlite3.connect(DB_PATH)
    conn.enable_load_extension(True)
    conn.load_extension(str(integrations.crsqlite.client.vendor_path()))
    enable_crdt(conn)
    changes = get_changes_since(conn, 0)
    apply_changes(conn, peer_changes)
    finalize(conn)
"""
from __future__ import annotations

import platform
import sqlite3
from pathlib import Path

# Diretorio do vendor: integrations/crsqlite/
# Funcao _resolve_vendor_dir() e chamada em cada vendor_path() para respeitar
# SINAPSE_HOME em tempo de execucao (importante para instalacoes onde
# o codigo esta em /usr/lib/python3/dist-packages/integrations/crsqlite/
# mas o vendor binario esta em /opt/hive-mind/integrations/crsqlite/).
import os as _os


def _resolve_vendor_dir() -> Path:
    """Resolve o diretorio do vendor em tempo de chamada.

    Ordem:
      1. SINAPSE_HOME/integrations/crsqlite/  -- instalacao real
      2. Caminho do __file__  -- modo editavel (uv pip install -e)
    """
    env_dir = _os.environ.get("SINAPSE_HOME")
    if env_dir:
        candidate = Path(env_dir) / "integrations" / "crsqlite"
        if candidate.exists():
            return candidate
    return Path(__file__).resolve().parent


# Backward-compat: VENDOR_DIR mantido como Path para imports externos.
# E o caminho do source (pode estar errado se SINAPSE_HOME apontar
# para outro local, mas vendor_path() abaixo sempre revalida).
VENDOR_DIR = Path(__file__).resolve().parent

# Tabelas CRR-elegiveis (ver P8.3 do roadmap). search_vec/search_fts sao
# VIRTUAIS e CR-SQLite nao suporta; capture-state.db e local-only
# (SeenStore). Estes ficam fora e cada maquina reconstroi o que precisar.
CRDT_TABLES = [
    "neurons",
    "synapses",
    "observations",
    "vault",
    "ambiguities",
    "visual_memories",
    "document_memories",
    "causal_edges",
    "goals",
]


def _lib_filename() -> str:
    """Detecta o nome do binario conforme plataforma.

    Mapeamento vem dos assets da release v0.16.3:
    - crsqlite-linux-x86_64.zip -> crsqlite.so (tambem aarch64)
    - crsqlite-darwin-x86_64.zip -> crsqlite.dylib (tambem aarch64)
    - crsqlite-win-x86_64.zip -> crsqlite.dll
    """
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "linux":
        # Linux x86_64 e aarch64 usam o mesmo nome dentro do zip.
        return "crsqlite.so"
    if system == "darwin":
        return "crsqlite.dylib"
    if system == "windows":
        return "crsqlite.dll"
    raise RuntimeError(f"Plataforma nao suportada: {system}/{machine}")


def vendor_path() -> Path:
    """Retorna o caminho absoluto do binario crsqlite para a plataforma atual.

    Resolve em tempo de chamada via _resolve_vendor_dir() para respeitar
    SINAPSE_HOME (mesmo se o modulo foi importado de outro caminho).
    """
    lib = _resolve_vendor_dir() / _lib_filename()
    if not lib.exists():
        raise RuntimeError(
            f"crsqlite nao encontrado em {lib}. "
            "Rode install.sh para baixar (secao CR-SQLite)."
        )
    return lib


def load_crsqlite_extension(conn: sqlite3.Connection) -> None:
    """Carrega a extensao. Deve ser a PRIMEIRA operacao apos abrir conexao."""
    conn.enable_load_extension(True)
    try:
        conn.load_extension(str(vendor_path()))
    finally:
        conn.enable_load_extension(False)


def enable_crdt(conn: sqlite3.Connection, tables: list[str] | None = None) -> None:
    """Carrega a extensao e converte tabelas para CRR.

    Por padrao, tenta todas as tabelas em CRDT_TABLES. Tabelas que nao
    existem no schema atual sao silenciosamente ignoradas (caso comum
    em testes que usam schema minimo, ou migracao parcial). Isso evita
    quebrar o codigo de teste/dry-run enquanto ainda tenta upgrade nas
    tabelas presentes.

    Idempotente: reexecutar e no-op (crsql_as_crr retorna a row existente
    em vez de falhar em tabela ja CRR).
    """
    load_crsqlite_extension(conn)
    targets = tables if tables is not None else CRDT_TABLES
    existing = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    for table in targets:
        if table not in existing:
            continue  # tabela nao existe neste DB (teste/migracao parcial)
        try:
            conn.execute(f"SELECT crsql_as_crr('{table}')")
        except sqlite3.OperationalError as e:
            # Falha real: PK nullable, NOT NULL sem DEFAULT, etc.
            # Re-raise para nao esconder bugs de schema.
            raise RuntimeError(
                f"crsql_as_crr falhou em {table!r}: {e}. "
                "Schema precisa PK NOT NULL DEFAULT e DEFAULT em toda NOT NULL."
            ) from e
    conn.commit()


def get_changes_since(conn: sqlite3.Connection, db_version: int) -> list[tuple]:
    """Retorna mudancas LOCAIS (exclui o que veio de outros peers).

    Filtro `AND site_id = crsql_site_id()` segue o notebook do tantaman
    e o README oficial do vlcn-io/cr-sqlite.
    """
    site = conn.execute("SELECT crsql_site_id()").fetchone()[0]
    return conn.execute(
        "SELECT * FROM crsql_changes "
        "WHERE db_version > ? AND site_id = ?",
        (db_version, site),
    ).fetchall()


# Tamanho do batch para commits durante apply_changes. Cada batch e uma
# transacao SQLite (BEGIN; N inserts via executemany; COMMIT).
#
# Performance medida (2026-06-25, 65k changes, DB ja populado):
#   batch=100:  ~0.64s
#   batch=1000: ~0.54s
# Nao ha complexidade quadratica observavel nesta escala. (Os ~190s
# relatados antes vinham do truque de arquivo temporario do Bloco C, nao
# de apply_changes.) 1000 e um bom balanco entre round-trips e tempo de WAL.
_APPLY_CHANGES_BATCH = 1000


def apply_changes(conn: sqlite3.Connection, changes: list[tuple]) -> int:
    """Aplica um batch de changes de outro peer. Idempotente: silenciosamente
    ignora entradas ja aplicadas (IntegrityError = conflito de chave).

    Para performance, commita a cada _APPLY_CHANGES_BATCH mudancas e
    usa executemany dentro de cada batch. Mudancas com conflito sao
    re-tentadas individualmente (executemany para tudo na primeira excecao).
    """
    applied = 0
    i = 0
    n = len(changes)
    while i < n:
        batch = changes[i:i + _APPLY_CHANGES_BATCH]
        i += _APPLY_CHANGES_BATCH
        try:
            # Tentativa otimista: executemany em todo o batch.
            conn.executemany(
                "INSERT INTO crsql_changes VALUES (?,?,?,?,?,?,?,?,?)",
                batch,
            )
            applied += len(batch)
        except sqlite3.IntegrityError:
            # Fallback: aplica uma a uma para isolar conflitos.
            for change in batch:
                try:
                    conn.execute(
                        "INSERT INTO crsql_changes VALUES (?,?,?,?,?,?,?,?,?)",
                        change,
                    )
                    applied += 1
                except sqlite3.IntegrityError:
                    # Mudanca antiga ja foi aplicada (LWW no mesmo col_version).
                    pass
        conn.commit()
    return applied


def current_db_version(conn: sqlite3.Connection) -> int:
    """Retorna o db_version atual (monotonic counter local)."""
    return conn.execute("SELECT crsql_db_version()").fetchone()[0]


def finalize(conn: sqlite3.Connection) -> None:
    """Chame antes de fechar a conexao para limpar triggers internos do CRR."""
    conn.execute("SELECT crsql_finalize()")
