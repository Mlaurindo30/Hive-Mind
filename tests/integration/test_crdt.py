"""CR-SQLite - testes de integracao (sem mocks, com binario real).

Cobre:
- Export de crsql_changes locais
- Import e convergencia entre dois DBs
- Conflito LWW preservado por site_id
- Version tracking (db_version incrementa)
- finalize() nao quebra em conexao subsequente

Pre-requisito: install.sh rodou e integrations/crsqlite/crsqlite.so existe.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

# Caminho do vendor (igual ao usado em integracoes reais).
VENDOR = Path(__file__).resolve().parents[2] / "integrations" / "crsqlite"

pytestmark = pytest.mark.skipif(
    not (VENDOR / "crsqlite.so").exists()
    and not (VENDOR / "crsqlite.dylib").exists()
    and not (VENDOR / "crsqlite.dll").exists(),
    reason="CR-SQLite nao baixado. Rode install.sh (secao CR-SQLite).",
)

# Schema minimo compativel com CRR (PK NOT NULL DEFAULT em todas colunas).
SCHEMA = """
CREATE TABLE neurons (
    id TEXT PRIMARY KEY NOT NULL DEFAULT '',
    label TEXT NOT NULL DEFAULT '',
    score REAL DEFAULT 0.0
);
"""


def _make_conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    # Import aqui dentro do teste - confere com o caminho real em runtime.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from integrations.crsqlite import client as crdt
    crdt.enable_crdt(conn)
    return conn


def _make_conn_existing(db_path: str) -> sqlite3.Connection:
    """Reabre um DB CRR ja existente (sem recriar schema), com extensoes."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    import sqlite_vec
    from integrations.crsqlite import client as crdt
    conn = sqlite3.connect(db_path)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    crdt.load_crsqlite_extension(conn)
    return conn


def test_export_changes_local_only():
    """Mudancas locais sao exportaveis com site_id correto."""
    conn = _make_conn(":memory:")
    try:
        conn.execute("INSERT INTO neurons (id, label, score) VALUES ('a1', 'foo', 0.1)")
        conn.commit()
        from integrations.crsqlite import client as crdt
        changes = crdt.get_changes_since(conn, 0)
        assert len(changes) >= 1
        # Primeiro campo e 'neurons', segundo e a PK serializada, etc.
        assert all(c[0] == "neurons" for c in changes)
        # Todas as mudancas devem ter site_id local (nao de peers).
        site = conn.execute("SELECT crsql_site_id()").fetchone()[0]
        assert all(c[6] == site for c in changes)
    finally:
        from integrations.crsqlite import client as crdt
        crdt.finalize(conn)


def test_apply_changes_converges_two_dbs():
    """DB B recebe mudancas de DB A e fica identico."""
    with tempfile.TemporaryDirectory() as tmp:
        a_path = os.path.join(tmp, "a.db")
        b_path = os.path.join(tmp, "b.db")
        a = _make_conn(a_path)
        b = _make_conn(b_path)
        try:
            a.execute(
                "INSERT INTO neurons (id, label, score) "
                "VALUES ('x1', 'caixa-preta', 0.42)"
            )
            a.execute(
                "INSERT INTO neurons (id, label, score) "
                "VALUES ('x2', 'voo-sp-1234', 0.87)"
            )
            a.commit()
            from integrations.crsqlite import client as crdt

            changes = crdt.get_changes_since(a, 0)
            assert len(changes) == 4  # 2 inserts x 2 cols (label + score)
            applied = crdt.apply_changes(b, changes)
            assert applied == 4

            # B agora tem as mesmas rows que A.
            a_rows = sorted(a.execute("SELECT id, label FROM neurons").fetchall())
            b_rows = sorted(b.execute("SELECT id, label FROM neurons").fetchall())
            assert a_rows == b_rows == [
                ("x1", "caixa-preta"),
                ("x2", "voo-sp-1234"),
            ]
        finally:
            from integrations.crsqlite import client as crdt
            crdt.finalize(a)
            crdt.finalize(b)


def test_conflict_lww_converges_both_sides():
    """Apos merge bidirecional completo, A e B convergem para o mesmo valor
    (LWW com col_version maior vence - propriedade de CRDT LWW)."""
    with tempfile.TemporaryDirectory() as tmp:
        a = _make_conn(os.path.join(tmp, "a.db"))
        b = _make_conn(os.path.join(tmp, "b.db"))
        try:
            # Sincronizacao inicial.
            a.execute("INSERT INTO neurons (id, label, score) VALUES ('c1', 'origem', 0.5)")
            b.execute("INSERT INTO neurons (id, label, score) VALUES ('c1', 'origem', 0.5)")
            a.commit()
            b.commit()
            from integrations.crsqlite import client as crdt
            crdt.apply_changes(b, crdt.get_changes_since(a, 0))
            crdt.apply_changes(a, crdt.get_changes_since(b, 0))

            # Edicao concorrente em A e B na mesma PK.
            a.execute("UPDATE neurons SET score = 0.99 WHERE id = 'c1'")
            b.execute("UPDATE neurons SET score = 0.11 WHERE id = 'c1'")
            a.commit()
            b.commit()

            # Aplica cruzadamente.
            crdt.apply_changes(a, crdt.get_changes_since(b, 0))
            crdt.apply_changes(b, crdt.get_changes_since(a, 0))

            # LWW: apos merge bidirecional, ambos convergiram para o mesmo
            # valor (o de col_version maior vence). Isso e a propriedade
            # central do CRDT LWW do CR-SQLite.
            a_score = a.execute("SELECT score FROM neurons WHERE id='c1'").fetchone()[0]
            b_score = b.execute("SELECT score FROM neurons WHERE id='c1'").fetchone()[0]
            assert a_score == b_score, (
                f"LWW falhou: A={a_score}, B={b_score} deveriam ser iguais"
            )
        finally:
            from integrations.crsqlite import client as crdt
            crdt.finalize(a)
            crdt.finalize(b)


def test_db_version_monotonic():
    """db_version incrementa a cada modificacao."""
    conn = _make_conn(":memory:")
    try:
        from integrations.crsqlite import client as crdt
        v0 = crdt.current_db_version(conn)
        conn.execute("INSERT INTO neurons (id, label) VALUES ('z1', 'one')")
        conn.commit()
        v1 = crdt.current_db_version(conn)
        assert v1 > v0
    finally:
        from integrations.crsqlite import client as crdt
        crdt.finalize(conn)


def _load_sync_module():
    """Módulo importável scripts.services.sinapse_sync (fonte única da CLI de sync)."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.services import sinapse_sync
    return sinapse_sync


def _make_file_db(path: str) -> None:
    """Cria um DB CRR em arquivo, pronto para reabrir."""
    conn = _make_conn(path)
    from integrations.crsqlite import client as crdt
    crdt.finalize(conn)
    conn.close()


def test_cli_import_preserves_id_and_propagates_update(monkeypatch):
    """Regressao: o caminho real do CLI (_export -> _import_changes) deve
    preservar a PK (o pk de crsql_changes e binario packed, nao a string id)
    E propagar UPDATEs em linhas existentes.

    Cobre o bug do INSERT OR IGNORE (2026-06-25): decodificava o pk como utf-8
    (corrompendo o id) e fazia no-op em linhas existentes (perdendo updates).
    O teste antigo so contava linhas, nunca verificava id nem update.
    """
    sync = _load_sync_module()
    import core.database as db
    from integrations.crsqlite import client as crdt

    with tempfile.TemporaryDirectory() as tmp:
        a_path = os.path.join(tmp, "a.db")
        b_path = os.path.join(tmp, "b.db")
        _make_file_db(a_path)
        _make_file_db(b_path)

        # A insere um neuron com id legivel.
        a = _make_conn_existing(a_path)
        a.execute("INSERT INTO neurons (id,label,score) VALUES ('n-real-id','v1',0.5)")
        a.commit()
        crdt.finalize(a)
        a.close()

        # _export de A.
        monkeypatch.setattr(db, "DB_PATH", a_path)
        payload1 = sync._export(0)
        assert len(payload1["changes"]) >= 2  # label + score

        # _import_changes para B (caminho real do CLI).
        monkeypatch.setattr(db, "DB_PATH", b_path)
        sync._import_changes(payload1)

        # B deve ter o neuron com o ID CORRETO (nao um pk binario corrompido).
        b = _make_conn_existing(b_path)
        row = b.execute("SELECT id, label, score FROM neurons").fetchone()
        assert row is not None, "neuron nao chegou em B"
        assert row[0] == "n-real-id", f"PK corrompida: {row[0]!r} (esperado 'n-real-id')"
        assert row[1] == "v1" and row[2] == 0.5
        crdt.finalize(b)
        b.close()

        # A faz UPDATE numa linha JA EXISTENTE.
        a = _make_conn_existing(a_path)
        a.execute("UPDATE neurons SET label='v2-editado', score=0.99 WHERE id='n-real-id'")
        a.commit()
        crdt.finalize(a)
        a.close()

        # Re-export + re-import: o UPDATE deve propagar para B.
        monkeypatch.setattr(db, "DB_PATH", a_path)
        payload2 = sync._export(0)
        monkeypatch.setattr(db, "DB_PATH", b_path)
        sync._import_changes(payload2)

        b = _make_conn_existing(b_path)
        row = b.execute("SELECT label, score FROM neurons WHERE id='n-real-id'").fetchone()
        crdt.finalize(b)
        b.close()
        assert row == ("v2-editado", 0.99), (
            f"update nao propagou via CLI: B={row} (esperado ('v2-editado', 0.99))"
        )


def test_finalize_does_not_break_subsequent_connections():
    """finalize() limpa a conexao mas nao corrompe o arquivo - reabrir funciona."""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "fb.db")
        c1 = _make_conn(path)
        c1.execute("INSERT INTO neurons (id, label) VALUES ('f1', 'persistida')")
        c1.commit()
        from integrations.crsqlite import client as crdt
        crdt.finalize(c1)
        # Reabrir e ler.
        c2 = sqlite3.connect(path)
        row = c2.execute("SELECT label FROM neurons WHERE id='f1'").fetchone()
        assert row[0] == "persistida"
