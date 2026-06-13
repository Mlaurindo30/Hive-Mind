import sqlite3

import sqlite_vec

from scripts import setup_umc


def test_verify_setup_does_not_delete_operational_vectors(monkeypatch, tmp_path):
    db_path = tmp_path / "umc.db"
    conn = sqlite3.connect(db_path)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.execute(
        "CREATE VIRTUAL TABLE search_vec USING vec0("
        "neuron_id TEXT PRIMARY KEY, embedding FLOAT[384])"
    )
    packed = setup_umc.serialize_f32([0.2] * 384)
    conn.execute(
        "INSERT INTO search_vec(neuron_id, embedding) VALUES ('existing', ?)",
        (packed,),
    )
    conn.commit()
    monkeypatch.setattr(setup_umc, "get_connection", lambda: conn)

    assert setup_umc.verify_setup() is True
    check = sqlite3.connect(db_path)
    check.enable_load_extension(True)
    sqlite_vec.load(check)
    check.enable_load_extension(False)
    assert check.execute("SELECT COUNT(*) FROM search_vec").fetchone()[0] == 1
