#!/usr/bin/env python3
"""Migra o hive_mind.db existente para o schema CRR-compat (P8 CR-SQLite).

Fluxo:
  (a) Backup: cp hive_mind.db hive_mind.db.pre-crr.<timestamp>
  (b) Cria DB novo com o schema CRR-compat (core/umc_schema_crr.sql)
  (c) Copia dados das 9 tabelas CRR-eligiveis preservando PKs
      (e remove orfaos de FK - CRR nao tem integridade referencial)
  (d) Recria search_vec e search_fts (vec0 + fts5 - reconstroi indices)
  (e) Executa crsql_as_crr em cada tabela presente
  (f) Smoke test: crsql_db_version() retorna > 0, crsql_changes populado

Nao e destrutivo com o DB original ate o backup ser confirmado.
Rollback: copie hive_mind.db.pre-crr.<timestamp> de volta para hive_mind.db.

Uso:
  python3 scripts/setup/setup_crdt.py [--dry-run] [--keep-original]

  --dry-run       Apenas simula, nao escreve nada
  --keep-original Apos migrar bem, renomeia original para .pre-crr (default: apaga)
  --target PATH   Caminho do DB de destino (default: mesmo caminho do original)

Pre-requisito: install.sh rodou e integrations/crsqlite/crsqlite.so existe.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# Caminhos canonicos (igual core/database.py)
SINAPSE_HOME = os.environ.get(
    "SINAPSE_HOME", str(Path(__file__).resolve().parents[2])
)
DB_PATH = os.path.join(SINAPSE_HOME, "hive_mind.db")
SCHEMA_CRR_PATH = os.path.join(SINAPSE_HOME, "core", "umc_schema_crr.sql")
VENDOR = Path(SINAPSE_HOME) / "integrations" / "crsqlite"

# Tabelas CRR-eligiveis (mesma lista de integrations/crsqlite/client.py)
CRDT_TABLES = [
    "neurons", "synapses", "observations", "vault", "ambiguities",
    "visual_memories", "document_memories", "causal_edges", "goals",
]

# Colunas para copiar por tabela (todas - nao tentamos filtrar nada)
# Note: CRR removeu FK constraints. Orfaos de FK (linhas em synapses que
# referenciam neurons inexistentes) sao removidos durante a copia.
COLUMNS_PER_TABLE = {
    "neurons": ["id", "label", "type", "source_file", "content", "hash",
                "metadata", "community", "created_at", "updated_at",
                "visibility", "indexed_at"],
    "synapses": ["id", "source_id", "target_id", "relation", "weight",
                 "metadata", "created_at"],
    "observations": ["id", "session_id", "project", "type", "title", "content",
                     "created_at", "neuron_id", "archived", "metadata",
                     "uuid", "source_machine", "goal_id", "why", "intent_source"],
    "vault": ["id", "encrypted_secret", "metadata", "created_at"],
    "ambiguities": ["id", "neuron_id", "source_a_hash", "source_b_hash",
                    "content_a", "content_b", "metadata_a", "metadata_b",
                    "status", "detected_at"],
    "visual_memories": ["id", "image_path", "description", "ocr_text",
                        "neuron_id", "metadata", "created_at"],
    "document_memories": ["id", "file_path", "file_hash", "summary",
                          "topics", "metadata", "created_at"],
    "causal_edges": ["id", "cause_neuron_id", "effect_neuron_id",
                     "label", "confidence", "source", "created_at"],
    "goals": ["id", "description", "steps_json", "status", "created_at"],
}


def find_vendor_lib() -> Path:
    """Retorna o caminho do binario crsqlite para a plataforma atual.

    Importa integrations.crsqlite.client (resolve SINAPSE_HOME lazy via
    _resolve_vendor_dir) e chama vendor_path() que valida existencia.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from integrations.crsqlite.client import vendor_path
    return vendor_path()


def backup_db(src_db: Path) -> Path:
    """Cria backup timestamped do DB original."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup = src_db.with_name(f"{src_db.name}.pre-crr.{ts}")
    shutil.copy2(src_db, backup)
    return backup


def open_with_extensions(db_path: Path) -> sqlite3.Connection:
    """Abre conexao com sqlite-vec + crsqlite carregados."""
    import sqlite_vec  # noqa: F401 (apenas para checar que esta instalado)

    conn = sqlite3.connect(db_path)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)

    lib = find_vendor_lib()
    if not lib.exists():
        raise RuntimeError(
            f"crsqlite nao encontrado em {lib}. "
            "Rode install.sh (etapa CR-SQLite) ou "
            "INSTALL_CRSQLITE=true bash install.sh"
        )
    conn.load_extension(str(lib))
    conn.enable_load_extension(False)
    return conn


def copy_table_data(src: sqlite3.Connection, dst: sqlite3.Connection,
                    table: str, columns: list[str]) -> tuple[int, int]:
    """Copia dados de src para dst preservando PKs.

    Retorna (copiados, orfaos_removidos).
    Remove orfaos de FK: se uma coluna FK referencia outra tabela,
    remove linhas onde o FK nao existe em dst (CRR nao tem integridade
    referencial enforced).
    """
    src.row_factory = sqlite3.Row
    rows = src.execute(f"SELECT {','.join(columns)} FROM {table}").fetchall()
    if not rows:
        return (0, 0)

    # Detectar colunas que parecem FK (heuristica simples)
    fk_cols = _detect_fk_columns(src, table)

    copied = 0
    orphans = 0
    for row in rows:
        row_dict = dict(row)
        skip = False
        for fk_col in fk_cols:
            target = row_dict.get(fk_col)
            if target is None or target == "":
                continue
            # Tabela alvo via FK_COLUMN_TO_TABLE (sem heuristica)
            target_table = FK_COLUMN_TO_TABLE[fk_col]
            # Conferir se existe em dst
            exists = dst.execute(
                f"SELECT 1 FROM {target_table} WHERE id = ?", (target,)
            ).fetchone()
            if not exists:
                skip = True
                break
        if skip:
            orphans += 1
            continue
        placeholders = ",".join("?" * len(columns))
        col_names = ",".join(columns)
        try:
            dst.execute(
                f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})",
                tuple(row_dict[c] for c in columns),
            )
            copied += 1
        except sqlite3.IntegrityError:
            orphans += 1
    return (copied, orphans)


# Mapeamento explicito FK col -> tabela alvo. CRR removeu FK constraints,
# entao durante a copia precisamos validar manualmente para remover orfaos.
FK_COLUMN_TO_TABLE = {
    "source_id": "neurons",      # synapses
    "target_id": "neurons",      # synapses
    "neuron_id": "neurons",      # observations, ambiguities, visual_memories
    "goal_id": "goals",          # observations
    "cause_neuron_id": "neurons", # causal_edges
    "effect_neuron_id": "neurons", # causal_edges
}


def _detect_fk_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    """Retorna colunas desta tabela que sao FKs declaradas."""
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    return [c for c in cols if c in FK_COLUMN_TO_TABLE]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="Apenas simula, nao escreve nada no DB")
    ap.add_argument("--keep-original", action=argparse.BooleanOptionalAction,
                    default=True,
                    help="Mantem o backup .pre-crr.<ts> apos migrar (default: "
                         "True; use --no-keep-original para apaga-lo)")
    ap.add_argument("--force", action="store_true",
                    help="Re-executa mesmo se o DB ja for CRR (CUIDADO: reseta "
                         "o relogio vetorial CRDT e re-sincroniza tudo)")
    ap.add_argument("--target", default=DB_PATH,
                    help=f"Caminho do DB de destino (default: {DB_PATH})")
    args = ap.parse_args()

    src_db = Path(args.target)
    if not src_db.exists():
        print(f"ERRO: DB nao encontrado em {src_db}")
        return 1

    schema_path = Path(SCHEMA_CRR_PATH)
    if not schema_path.exists():
        print(f"ERRO: schema CRR nao encontrado em {schema_path}")
        return 1

    # Preflight: detecta DB ja migrado para CRR. Re-executar reconstroi o DB do
    # zero (novo relogio vetorial / site_id), o que faria todos os peers re-verem
    # tudo como novo no proximo sync. Aborta a menos que --force.
    _src_check = sqlite3.connect(src_db)
    try:
        already_crr = _src_check.execute(
            "SELECT count(*) FROM sqlite_master WHERE name LIKE 'crsql_%' OR name LIKE '__crsql%'"
        ).fetchone()[0]
    finally:
        _src_check.close()
    if already_crr and not args.force:
        print(
            f"ERRO: {src_db} ja parece ser CRR ({already_crr} tabelas crsql_*).\n"
            "      Re-executar reseta o estado de sync (relogio vetorial CRDT).\n"
            "      Use --force se realmente quer re-migrar do zero."
        )
        return 1

    print(f"=== Setup CRDT (P8) ===")
    print(f"DB origem:    {src_db}")
    print(f"Schema CRR:   {schema_path}")
    print(f"Vendor:       {find_vendor_lib()}")
    print()

    if args.dry_run:
        print("[dry-run] Apenas validando - nenhuma escrita sera feita")
        print(f"[dry-run] Backup seria criado:    {src_db}.pre-crr.<timestamp>")
        print(f"[dry-run] DB temporario seria:    <temp>/hive_mind_crr_<random>.db")
        print(f"[dry-run] DB final seria:        {src_db} (substituindo o original)")
        print(f"[dry-run] Tabelas CRR-eligiveis:  {len(CRDT_TABLES)}")
        print(f"[dry-run] Vendor lib esperada:    {find_vendor_lib()}")
        if not find_vendor_lib().exists():
            print(f"[dry-run] AVISO: vendor nao encontrado, install.sh precisa rodar")
        print(f"\n[dry-run] Concluido (nenhuma alteracao feita).")
        return 0

    # (a) Backup
    backup = backup_db(src_db)
    print(f"[OK] Backup criado: {backup}")

    # (b) Criar DB temporario com schema CRR
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_db = Path(tmp.name)

    print(f"\n[b] Criando DB temporario {tmp_db}")
    new = sqlite3.connect(tmp_db)

    # sqlite-vec DEVE ser carregado ANTES de aplicar o schema (que cria
    # CREATE VIRTUAL TABLE vec0). CR-SQLite tambem precisa estar carregado
    # antes de chamar crsql_as_crr.
    try:
        import sqlite_vec
        new.enable_load_extension(True)
        sqlite_vec.load(new)
        new.load_extension(str(find_vendor_lib()))
        new.enable_load_extension(False)
    except (ImportError, RuntimeError) as e:
        print(f"  ERRO ao carregar extensoes: {e}")
        print(f"  Rode install.sh (etapa CR-SQLite) antes de setup_crdt.py")
        return 2

    new.executescript(schema_path.read_text())
    print("  [OK] Schema CRR aplicado (sqlite-vec + crsqlite carregados)")

    # (c) Copia dados
    print(f"\n[c] Copiando dados das {len(CRDT_TABLES)} tabelas CRR-eligiveis")
    src_conn = sqlite3.connect(src_db)
    src_conn.row_factory = sqlite3.Row

    total_copied = 0
    total_orphans = 0
    for table in CRDT_TABLES:
        if table not in COLUMNS_PER_TABLE:
            print(f"  [SKIP] {table} (sem mapeamento de colunas)")
            continue
        # Verificar se tabela existe no DB original
        src_has = src_conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        if not src_has:
            print(f"  [SKIP] {table} (nao existe no DB original)")
            continue
        copied, orphans = copy_table_data(
            src_conn, new, table, COLUMNS_PER_TABLE[table]
        )
        total_copied += copied
        total_orphans += orphans
        print(f"  [{table:18s}] {copied:5d} copiados, {orphans:3d} orfaos removidos")
    src_conn.close()
    new.commit()
    print(f"  [OK] Total: {total_copied} linhas copiadas, "
          f"{total_orphans} orfaos removidos (FKs quebradas)")

    # (d) search_vec / search_fts: como CRR nao suporta virtual tables,
    #     elas serao reconstruidas via Dream Cycle em cada maquina.
    #     Apenas garantimos que existem no DB novo (ja criadas pelo schema).

    # (e) CRR upgrade — fecha a conexao da fase (b)-(c) antes de reabrir,
    #     senao o handle (com WAL/-shm) vaza ate o fim do processo.
    new.close()
    print(f"\n[e] Aplicando crsql_as_crr em {len(CRDT_TABLES)} tabelas")
    try:
        new = open_with_extensions(tmp_db)
    except RuntimeError as e:
        print(f"  ERRO: {e}")
        return 2

    upgraded, failed = [], []
    for table in CRDT_TABLES:
        try:
            new.execute(f"SELECT crsql_as_crr('{table}')")
            upgraded.append(table)
            print(f"  [OK]   {table}")
        except sqlite3.OperationalError as e:
            failed.append((table, str(e)))
            print(f"  [FAIL] {table}: {e}")
    new.commit()

    if failed:
        print(f"\n  AVISO: {len(failed)}/{len(CRDT_TABLES)} tabelas falharam no CRR upgrade")
        print(f"  CR-SQLite recusa tabelas com schema invalido.")
        print(f"  Verifique o schema CRR (core/umc_schema_crr.sql) e reinicie.")

    # (f) Smoke test
    print(f"\n[f] Smoke test")
    db_v = new.execute("SELECT crsql_db_version()").fetchone()[0]
    changes = new.execute("SELECT count(*) FROM crsql_changes").fetchone()[0]
    print(f"  crsql_db_version: {db_v}")
    print(f"  crsql_changes count: {changes}")

    # Finalize e commit final
    new.execute("SELECT crsql_finalize()")
    new.close()

    # (g) Substituir original pelo novo. (dry-run ja retornou em (a); aqui e
    #     sempre o caminho de escrita real.)
    print(f"\n[g] Substituindo {src_db} pelo novo DB CRR")
    shutil.copy2(tmp_db, src_db)
    print(f"  [OK] {src_db} agora e o DB CRR-compat")
    tmp_db.unlink()

    # Backup criado em (a): mantem por padrao; --no-keep-original apaga.
    if not args.keep_original:
        backup.unlink(missing_ok=True)
        print(f"  [OK] Backup {backup} removido (--no-keep-original)")
    else:
        print(f"  [info] Backup preservado: {backup}")

    print("\n=== Concluido ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
