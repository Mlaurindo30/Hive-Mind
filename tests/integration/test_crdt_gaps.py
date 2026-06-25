"""CR-SQLite gap coverage — P8 re-passagem (2026-06-25).

Preenche lacunas de test_crdt.py e test_sync_endpoints.py:

  1. Bidirectional unique-row exchange: A e B trocam linhas diferentes;
     ambos convergem para o conjunto completo.
  2. DELETE tombstone propagation: DELETE em A deve chegar em B.
  3. Incremental --since: export(since=V) retorna apenas mudancas > V.
  4. Idempotencia: importar o mesmo payload duas vezes nao duplica/corrompe.
  5. Observations table + colunas NULL: tabela diferente de neurons.
  6. Full column preservation: TODAS as colunas sobrevivem ao round-trip
     (regressao do antigo 'latest' que so preservava a coluna de maior
     col_version).
  7. Empty changes payload: importar lista vazia retorna applied=0.
  8. Serialization bytes/None: _to_json_safe/_from_json_safe roundtrip.

Pre-requisito: integrations/crsqlite/crsqlite.so existe (mesmo que test_crdt.py).
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from pathlib import Path
import importlib.util

import pytest

VENDOR = Path(__file__).resolve().parents[2] / "integrations" / "crsqlite"
PROJECT_ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.skipif(
    not (VENDOR / "crsqlite.so").exists()
    and not (VENDOR / "crsqlite.dylib").exists()
    and not (VENDOR / "crsqlite.dll").exists(),
    reason="CR-SQLite nao baixado. Rode install.sh (secao CR-SQLite).",
)

sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Schemas minimos CRR-compativeis (PK NOT NULL DEFAULT; NOT NULL com DEFAULT)
# ---------------------------------------------------------------------------

SCHEMA_NEURONS = """
CREATE TABLE neurons (
    id    TEXT PRIMARY KEY NOT NULL DEFAULT '',
    label TEXT NOT NULL DEFAULT '',
    score REAL DEFAULT 0.0,
    notes TEXT
);
"""

SCHEMA_OBSERVATIONS = """
CREATE TABLE observations (
    id       TEXT PRIMARY KEY NOT NULL DEFAULT '',
    title    TEXT,
    content  TEXT,
    project  TEXT,
    archived INTEGER DEFAULT 0
);
"""

SCHEMA_GOALS = """
CREATE TABLE goals (
    id          TEXT PRIMARY KEY NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    steps_json  TEXT NOT NULL DEFAULT '[]',
    status      TEXT NOT NULL DEFAULT 'active',
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _crdt():
    """Importa integrations.crsqlite.client (lazy para respeitar pytestmark)."""
    from integrations.crsqlite import client as crdt
    return crdt


def _make_conn(db_path: str, schema: str = SCHEMA_NEURONS) -> sqlite3.Connection:
    """Cria/abre DB, aplica schema CRR e habilita CRDT."""
    conn = sqlite3.connect(db_path)
    conn.executescript(schema)
    _crdt().enable_crdt(conn)
    return conn


def _make_file_db(path: str, schema: str = SCHEMA_NEURONS) -> None:
    """Prepara um DB CRR em arquivo e fecha a conexao."""
    conn = _make_conn(path, schema)
    _crdt().finalize(conn)
    conn.close()


def _reopen(path: str) -> sqlite3.Connection:
    """Reabre um DB CRR existente (sem recriar schema) carregando a extensao."""
    import sqlite_vec
    conn = sqlite3.connect(path)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    _crdt().load_crsqlite_extension(conn)
    return conn


def _load_sync_module():
    """Carrega scripts/services/sinapse-sync.py via importlib (nome com hifen)."""
    path = PROJECT_ROOT / "scripts" / "services" / "sinapse-sync.py"
    spec = importlib.util.spec_from_file_location("sinapse_sync", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# 1. Bidirectional unique-row exchange
# ---------------------------------------------------------------------------

def test_bidirectional_unique_row_exchange():
    """A e B partem de DBs vazios, cada um insere linhas proprias.
    Apos A→B e B→A, ambos devem ter TODAS as linhas.

    Difere de test_conflict_lww_converges_both_sides (que testa a mesma PK)
    e de test_apply_changes_converges_two_dbs (so A→B, nao B→A).
    """
    crdt = _crdt()
    conn_a = _make_conn(":memory:")
    conn_b = _make_conn(":memory:")
    try:
        conn_a.execute("INSERT INTO neurons (id, label, score) VALUES ('a1', 'alpha', 0.1)")
        conn_a.execute("INSERT INTO neurons (id, label, score) VALUES ('a2', 'beta',  0.2)")
        conn_a.commit()

        conn_b.execute("INSERT INTO neurons (id, label, score) VALUES ('b1', 'gamma', 0.3)")
        conn_b.execute("INSERT INTO neurons (id, label, score) VALUES ('b2', 'delta', 0.4)")
        conn_b.commit()

        # A→B
        changes_from_a = crdt.get_changes_since(conn_a, 0)
        crdt.apply_changes(conn_b, changes_from_a)
        # B→A
        changes_from_b = crdt.get_changes_since(conn_b, 0)
        crdt.apply_changes(conn_a, changes_from_b)

        expected_ids = {"a1", "a2", "b1", "b2"}
        a_ids = {r[0] for r in conn_a.execute("SELECT id FROM neurons").fetchall()}
        b_ids = {r[0] for r in conn_b.execute("SELECT id FROM neurons").fetchall()}

        assert a_ids == expected_ids, f"A faltam rows: {expected_ids - a_ids}"
        assert b_ids == expected_ids, f"B faltam rows: {expected_ids - b_ids}"
    finally:
        crdt.finalize(conn_a)
        crdt.finalize(conn_b)


# ---------------------------------------------------------------------------
# 2. DELETE tombstone propagation
# ---------------------------------------------------------------------------

def test_delete_propagates_via_apply_changes():
    """DELETE em A deve chegar em B via crsql_changes (tombstone).

    CR-SQLite rastreia deletes como tombstones. Se get_changes_since nao
    incluir tombstones ou apply_changes nao os processar, este teste falha
    — o que seria um bug de producao (silently missing deletes during sync).
    """
    crdt = _crdt()
    with tempfile.TemporaryDirectory() as tmp:
        a_path = os.path.join(tmp, "a.db")
        b_path = os.path.join(tmp, "b.db")
        conn_a = _make_conn(a_path)
        conn_b = _make_conn(b_path)
        try:
            # Passo 1: A insere, sincroniza para B.
            conn_a.execute(
                "INSERT INTO neurons (id, label, score) VALUES ('del-me', 'temp', 0.5)"
            )
            conn_a.execute(
                "INSERT INTO neurons (id, label, score) VALUES ('keep-me', 'perm', 0.9)"
            )
            conn_a.commit()

            v_after_insert = crdt.current_db_version(conn_a)
            crdt.apply_changes(conn_b, crdt.get_changes_since(conn_a, 0))

            b_ids_before = {
                r[0] for r in conn_b.execute("SELECT id FROM neurons").fetchall()
            }
            assert "del-me" in b_ids_before, "B deveria ter del-me antes do delete"
            assert "keep-me" in b_ids_before

            # Passo 2: A deleta 'del-me'.
            conn_a.execute("DELETE FROM neurons WHERE id='del-me'")
            conn_a.commit()

            # Passo 3: Exporta apenas o que mudou apos o sync inicial.
            changes_after_delete = crdt.get_changes_since(conn_a, v_after_insert)
            assert len(changes_after_delete) >= 1, (
                "get_changes_since deveria incluir tombstone do DELETE"
            )

            # Passo 4: Aplica em B — B deve perder 'del-me'.
            crdt.apply_changes(conn_b, changes_after_delete)
            b_ids_after = {
                r[0] for r in conn_b.execute("SELECT id FROM neurons").fetchall()
            }

            assert "del-me" not in b_ids_after, (
                "DELETE nao propagou: 'del-me' ainda existe em B apos aplicar tombstone"
            )
            assert "keep-me" in b_ids_after, "'keep-me' foi removido incorretamente"
        finally:
            crdt.finalize(conn_a)
            crdt.finalize(conn_b)


# ---------------------------------------------------------------------------
# 3. Incremental --since export
# ---------------------------------------------------------------------------

def test_incremental_since_export_filters_old_changes():
    """get_changes_since(conn, V) retorna apenas mudancas com db_version > V.

    Cenario:
      - Insere batch1 em A, grava versao V1.
      - Insere batch2 em A.
      - get_changes_since(A, V1) deve conter apenas batch2.
      - Aplica em B (vazio): B fica apenas com batch2.
    """
    crdt = _crdt()
    conn_a = _make_conn(":memory:")
    conn_b = _make_conn(":memory:")
    try:
        # Batch 1.
        conn_a.execute("INSERT INTO neurons (id, label, score) VALUES ('old1', 'first',  0.1)")
        conn_a.execute("INSERT INTO neurons (id, label, score) VALUES ('old2', 'second', 0.2)")
        conn_a.commit()
        v1 = crdt.current_db_version(conn_a)

        # Versao deve incrementar.
        assert v1 > 0, "db_version deveria ter incrementado apos batch1"

        # Nenhuma mudanca apos V1 ainda.
        changes_between_batches = crdt.get_changes_since(conn_a, v1)
        assert changes_between_batches == [], (
            "get_changes_since(V1) deveria retornar [] antes do batch2"
        )

        # Batch 2.
        conn_a.execute("INSERT INTO neurons (id, label, score) VALUES ('new1', 'third',  0.3)")
        conn_a.execute("INSERT INTO neurons (id, label, score) VALUES ('new2', 'fourth', 0.4)")
        conn_a.commit()

        # Apenas batch2.
        incremental = crdt.get_changes_since(conn_a, v1)
        incremental_ids_covered = {c[1] for c in incremental}  # c[1] e o pk packed

        # O export total (since=0) deve ser maior que o incremental.
        full = crdt.get_changes_since(conn_a, 0)
        assert len(full) > len(incremental), (
            "export incremental deveria ser menor que o total"
        )

        # Aplica incremental em B (que esta vazio).
        crdt.apply_changes(conn_b, incremental)
        b_ids = {r[0] for r in conn_b.execute("SELECT id FROM neurons").fetchall()}

        assert "new1" in b_ids, "new1 deveria estar em B (batch2)"
        assert "new2" in b_ids, "new2 deveria estar em B (batch2)"
        assert "old1" not in b_ids, "old1 NAO deveria estar em B (esta antes de V1)"
        assert "old2" not in b_ids, "old2 NAO deveria estar em B (esta antes de V1)"
    finally:
        crdt.finalize(conn_a)
        crdt.finalize(conn_b)


# ---------------------------------------------------------------------------
# 4. Idempotencia
# ---------------------------------------------------------------------------

def test_import_idempotent():
    """Importar o mesmo payload duas vezes nao duplica linhas nem corrompe dados.

    apply_changes usa IntegrityError como sinal de 'ja aplicado'; o fallback
    individual descarta conflitos silenciosamente. O resultado deve ser identico
    apos a segunda aplicacao.
    """
    crdt = _crdt()
    conn_a = _make_conn(":memory:")
    conn_b = _make_conn(":memory:")
    try:
        conn_a.execute("INSERT INTO neurons (id, label, score) VALUES ('dup1', 'idem', 0.7)")
        conn_a.execute("INSERT INTO neurons (id, label, score) VALUES ('dup2', 'potm', 0.8)")
        conn_a.commit()

        changes = crdt.get_changes_since(conn_a, 0)
        assert len(changes) >= 2

        # Primeira importacao.
        crdt.apply_changes(conn_b, changes)
        count_after_1 = conn_b.execute("SELECT COUNT(*) FROM neurons").fetchone()[0]

        # Segunda importacao — deve ser no-op.
        crdt.apply_changes(conn_b, changes)
        count_after_2 = conn_b.execute("SELECT COUNT(*) FROM neurons").fetchone()[0]

        assert count_after_1 == count_after_2 == 2, (
            f"Segunda importacao alterou count: antes={count_after_1}, "
            f"depois={count_after_2} (esperado 2)"
        )

        # Valores nao corrompidos.
        row = conn_b.execute(
            "SELECT label, score FROM neurons WHERE id='dup1'"
        ).fetchone()
        assert row == ("idem", 0.7), f"Dados corrompidos apos dupla importacao: {row}"
    finally:
        crdt.finalize(conn_a)
        crdt.finalize(conn_b)


# ---------------------------------------------------------------------------
# 5. Observations table round-trip com colunas NULL
# ---------------------------------------------------------------------------

def test_observations_table_roundtrip_with_null_columns():
    """Tabela observations (nao neurons) com colunas nullable NULL sobrevive
    ao round-trip export→import sem perder valores nem introduzir erros.

    Valida que enable_crdt funciona em tabelas alem de neurons e que
    _to_json_safe(None) / _from_json_safe(None) preservam NULL corretamente.
    """
    sync = _load_sync_module()
    crdt = _crdt()

    with tempfile.TemporaryDirectory() as tmp:
        a_path = os.path.join(tmp, "obs_a.db")
        b_path = os.path.join(tmp, "obs_b.db")
        _make_file_db(a_path, SCHEMA_OBSERVATIONS)
        _make_file_db(b_path, SCHEMA_OBSERVATIONS)

        # A insere uma observation com varias colunas NULL.
        a = _reopen(a_path)
        a.execute(
            "INSERT INTO observations (id, title, content, project, archived) "
            "VALUES ('obs-1', 'titulo teste', NULL, NULL, 0)"
        )
        a.commit()
        crdt.finalize(a)
        a.close()

        import core.database as db
        from unittest.mock import patch

        with patch.object(db, "DB_PATH", a_path):
            payload = sync._export(0)

        assert len(payload["changes"]) >= 1, "nenhum change exportado de observations"

        with patch.object(db, "DB_PATH", b_path):
            result = sync._import_changes(payload)

        assert result["applied"] >= 1, "nenhum change aplicado em B"

        b = _reopen(b_path)
        row = b.execute(
            "SELECT id, title, content, project, archived FROM observations WHERE id='obs-1'"
        ).fetchone()
        crdt.finalize(b)
        b.close()

        assert row is not None, "observation nao chegou em B"
        assert row[0] == "obs-1"
        assert row[1] == "titulo teste"
        assert row[2] is None, f"content deveria ser NULL, chegou: {row[2]!r}"
        assert row[3] is None, f"project deveria ser NULL, chegou: {row[3]!r}"
        assert row[4] == 0


# ---------------------------------------------------------------------------
# 6. Full column preservation
# ---------------------------------------------------------------------------

def test_full_column_preservation_all_columns_survive():
    """Todas as colunas de uma linha sobrevivem ao ciclo export→import,
    inclusive a coluna 'notes' (nullable) e 'score' (REAL).

    Regressao do bug antigo do dict 'latest' que so preservava a coluna
    com maior col_version. Com apply_changes esse bug nao pode ocorrer,
    mas o teste documenta e protege contra regressoes futuras.
    """
    crdt = _crdt()
    conn_a = _make_conn(":memory:", SCHEMA_NEURONS)
    conn_b = _make_conn(":memory:", SCHEMA_NEURONS)
    try:
        conn_a.execute(
            "INSERT INTO neurons (id, label, score, notes) "
            "VALUES ('full-1', 'complete-row', 0.95, 'nota importantissima')"
        )
        conn_a.commit()

        changes = crdt.get_changes_since(conn_a, 0)
        crdt.apply_changes(conn_b, changes)

        row = conn_b.execute(
            "SELECT id, label, score, notes FROM neurons WHERE id='full-1'"
        ).fetchone()

        assert row is not None, "linha nao chegou em B"
        assert row[0] == "full-1",   f"id errado: {row[0]!r}"
        assert row[1] == "complete-row", f"label errado: {row[1]!r}"
        assert abs(row[2] - 0.95) < 1e-9, f"score errado: {row[2]}"
        assert row[3] == "nota importantissima", f"notes errado: {row[3]!r}"
    finally:
        crdt.finalize(conn_a)
        crdt.finalize(conn_b)


# ---------------------------------------------------------------------------
# 7. Empty changes payload
# ---------------------------------------------------------------------------

def test_empty_changes_payload_returns_zero():
    """_import_changes com changes=[] deve retornar applied=0 sem erro."""
    sync = _load_sync_module()

    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "empty.db")
        _make_file_db(db_path)

        import core.database as db_mod
        from unittest.mock import patch

        with patch.object(db_mod, "DB_PATH", db_path):
            result = sync._import_changes({"changes": []})

    assert result == {"applied": 0, "received": 0}, (
        f"payload vazio retornou resultado inesperado: {result}"
    )


# ---------------------------------------------------------------------------
# 8. Serialization: _to_json_safe / _from_json_safe com bytes e None
# ---------------------------------------------------------------------------

def test_serialization_bytes_roundtrip():
    """Bytes (pk packed do CR-SQLite) sobrevivem ao ciclo hex→dict→bytes."""
    sync = _load_sync_module()
    # O pk de crsql_changes para id='abc' e um blob binario packed.
    # Simulamos um blob tipico.
    original = b"\x01\x0b\x02n1"
    encoded = sync._to_json_safe(original)
    assert isinstance(encoded, dict), "bytes deveria virar dict"
    assert "__bytes__" in encoded, "chave __bytes__ ausente"
    assert encoded["__bytes__"] == original.hex()
    decoded = sync._from_json_safe(encoded)
    assert decoded == original, f"roundtrip falhou: {decoded!r} != {original!r}"


def test_serialization_none_passthrough():
    """None (coluna nullable) passa por _to_json_safe/_from_json_safe sem alteracao."""
    sync = _load_sync_module()
    assert sync._to_json_safe(None) is None
    assert sync._from_json_safe(None) is None


def test_serialization_scalar_passthrough():
    """Scalares (int, float, str) passam sem modificacao."""
    sync = _load_sync_module()
    for val in (42, 3.14, "hello world", "", 0):
        assert sync._to_json_safe(val) == val
        assert sync._from_json_safe(val) == val


# ---------------------------------------------------------------------------
# 9. Goals table round-trip via CLI
# ---------------------------------------------------------------------------

def test_goals_table_roundtrip_via_cli():
    """Tabela goals (outra CRDT table) sobrevive ao ciclo CLI _export/_import."""
    sync = _load_sync_module()
    crdt = _crdt()

    with tempfile.TemporaryDirectory() as tmp:
        a_path = os.path.join(tmp, "goals_a.db")
        b_path = os.path.join(tmp, "goals_b.db")
        _make_file_db(a_path, SCHEMA_GOALS)
        _make_file_db(b_path, SCHEMA_GOALS)

        a = _reopen(a_path)
        a.execute(
            "INSERT INTO goals (id, description, steps_json, status) "
            "VALUES ('g1', 'Conquistar o mundo', '[\"passo1\"]', 'active')"
        )
        a.commit()
        crdt.finalize(a)
        a.close()

        import core.database as db
        from unittest.mock import patch

        with patch.object(db, "DB_PATH", a_path):
            payload = sync._export(0)

        assert len(payload["changes"]) >= 1, "nenhum change exportado de goals"

        with patch.object(db, "DB_PATH", b_path):
            result = sync._import_changes(payload)

        assert result["applied"] >= 1

        b = _reopen(b_path)
        row = b.execute(
            "SELECT id, description, steps_json, status FROM goals WHERE id='g1'"
        ).fetchone()
        crdt.finalize(b)
        b.close()

        assert row is not None, "goal nao chegou em B"
        assert row[0] == "g1"
        assert row[1] == "Conquistar o mundo"
        assert row[2] == '[\"passo1\"]'
        assert row[3] == "active"
