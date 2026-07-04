"""R11.3 — P2P conflict detection routes to ambiguities, never overwrites silently.

Spec: specs/post-audit-stabilization.md R11.3.

Syncthing is installed on this machine (`syncthing --version`), so this test
runs for real rather than being skipped as MAY. It does not spin up two live
Syncthing daemons (that is exercised manually per docs/07-p2p-sync-setup.md);
instead it reproduces the artifact Syncthing itself produces on a real
collision — a `<neuron>.sync-conflict-<date>-<time>-<device>.md` file — and
drives the project's actual conflict router (`scripts.health.audit_memory`
+ `core.database.register_ambiguity`) against an isolated, real SQLite file
(no mocks on the write path) to prove the routing end-to-end.
"""

from __future__ import annotations

import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.real

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _make_isolated_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE neurons (
            id TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            type TEXT NOT NULL,
            source_file TEXT,
            content TEXT,
            hash TEXT,
            metadata JSON,
            community INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE ambiguities (
            id TEXT PRIMARY KEY,
            neuron_id TEXT NOT NULL,
            source_a_hash TEXT NOT NULL,
            source_b_hash TEXT NOT NULL,
            content_a TEXT NOT NULL,
            content_b TEXT NOT NULL,
            metadata_a JSON,
            metadata_b JSON,
            status TEXT DEFAULT 'pending',
            detected_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            workspace_id TEXT NOT NULL DEFAULT 'default'
        );
        CREATE TABLE search_vec (
            neuron_id TEXT PRIMARY KEY,
            embedding BLOB
        );
        """
    )
    conn.commit()
    conn.close()


def test_syncthing_available():
    """Precondition for this test to run as MUST rather than skipped MAY."""
    proc = subprocess.run(["syncthing", "--version"], capture_output=True, text=True, timeout=15)
    assert proc.returncode == 0, f"syncthing --version failed: {proc.stderr}"


def test_p2p_conflict_routes_to_ambiguities_without_silent_overwrite(tmp_path):
    from scripts.health import audit_memory
    import core.database as coredb

    db_path = tmp_path / "hive_mind.db"
    _make_isolated_db(db_path)

    atlas = tmp_path / "cerebro" / "cortex" / "temporal"
    atlas.mkdir(parents=True)
    conflicts_dir = tmp_path / "cerebro" / "cortex" / "insula" / "conflitos"

    neuron_id = "p2p-conflict-neuron"
    canonical_content = "# Node A\n\nConteúdo escrito no nó A."
    canonical_hash = "hash-node-a"

    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO neurons (id, label, type, content, hash) VALUES (?, ?, ?, ?, ?)",
        (neuron_id, "P2P Conflict Neuron", "fact", canonical_content, canonical_hash),
    )
    conn.commit()
    conn.close()

    # Node B's divergent edit, arriving as Syncthing would name it after a
    # real collision: <name>.sync-conflict-<date>-<time>-<short device id>.md
    conflict_name = f"{neuron_id}.sync-conflict-20260704-093000-NODEB12.md"
    conflict_content = "# Node B\n\nConteúdo divergente escrito no nó B."
    (atlas / conflict_name).write_text(conflict_content, encoding="utf-8")

    def _isolated_connection():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    with patch.object(audit_memory, "get_connection", _isolated_connection), \
         patch.object(audit_memory, "SINAPSE_HOME", str(tmp_path)), \
         patch.object(coredb, "DB_PATH", str(db_path)):
        # register_ambiguity is NOT mocked: it runs for real against db_path.
        audit_memory.run_audit(fix=True)

    # 1. Conflict file moved out of the vault, never left for a human to
    #    accidentally treat as canonical.
    assert not (atlas / conflict_name).exists(), "conflict file must be moved out of atlas"
    assert (conflicts_dir / conflict_name).exists(), "conflict file must land in cortex/insula/conflitos/"

    # 2. Real ambiguities row registered — both versions preserved, neither
    #    silently discarded.
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    amb = conn.execute(
        "SELECT * FROM ambiguities WHERE neuron_id = ?", (neuron_id,)
    ).fetchone()
    assert amb is not None, "conflict must be registered in ambiguities, not dropped"
    contents = {amb["content_a"], amb["content_b"]}
    assert canonical_content in contents
    assert conflict_content in contents
    assert amb["status"] == "pending"

    # 3. The canonical neuron row was NOT silently overwritten by the
    #    conflicting version.
    neuron = conn.execute(
        "SELECT content, hash FROM neurons WHERE id = ?", (neuron_id,)
    ).fetchone()
    assert neuron["content"] == canonical_content
    assert neuron["hash"] == canonical_hash
    conn.close()
