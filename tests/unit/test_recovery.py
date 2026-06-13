import sqlite3
from pathlib import Path

import sqlite_vec

from scripts.recovery import (
    backup_database,
    rebuild_indexes,
    restore_database,
    verify_database,
)


def _make_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.executescript(
        """
        CREATE TABLE neurons (
            id TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            content TEXT,
            indexed_at TIMESTAMP
        );
        CREATE VIRTUAL TABLE search_fts USING fts5(
            neuron_id UNINDEXED, label, content
        );
        CREATE VIRTUAL TABLE search_vec USING vec0(
            neuron_id TEXT PRIMARY KEY,
            embedding FLOAT[384]
        );
        CREATE TABLE observations (id TEXT PRIMARY KEY);
        """
    )
    conn.execute(
        "INSERT INTO neurons(id,label,content) VALUES ('n1','Alpha','first memory')"
    )
    conn.execute(
        "INSERT INTO search_fts(neuron_id,label,content) VALUES ('stale','Stale','bad')"
    )
    conn.commit()
    conn.close()


def _embed(texts):
    for index, _ in enumerate(texts):
        vector = [0.0] * 384
        vector[index % 384] = 1.0
        yield vector


def test_backup_restore_and_rebuild_indexes(tmp_path):
    source = tmp_path / "source.db"
    _make_db(source)

    backup = backup_database(source, tmp_path / "backups")
    assert verify_database(backup)["integrity_check"] == "ok"

    source.unlink()
    restore_database(backup, source)
    report = rebuild_indexes(source, embed_batch=_embed)

    assert report["integrity_check"] == "ok"
    assert report["counts"]["neurons"] == 1
    assert report["counts"]["search_fts"] == 1
    assert report["counts"]["search_vec"] == 1
    assert report["missing_fts"] == 0
    assert report["vector_probe"] == "ok"
    assert (tmp_path / "hnsw_neurons.idx").exists()
    assert (tmp_path / "hnsw_neurons.map.json").exists()
