"""Audit artifact cleanup helper for E2E tests.

Gate 3 of the Windows gates audit: safe, transactional removal of
AUDIT-* artifacts from UMC + vault + vectors, respecting FK order.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path


class AuditCleanup:
    """Track and remove AUDIT-* artifacts created during E2E tests.

    Usage (as a context manager or in ``finally``)::

        cleanup = AuditCleanup(db_path, vault_root)
        cleanup.register_neuron(neuron_id)
        cleanup.register_file(md_path)
        # ... test body ...
        cleanup.execute()      # idempotent, rollback-safe
    """

    def __init__(self, db_path: str | Path, vault_root: str | Path):
        self.db_path = str(db_path)
        self.vault_root = Path(vault_root)
        self._neuron_ids: list[str] = []
        self._file_paths: list[Path] = []
        self._observation_ids: list[int] = []

    def register_neuron(self, neuron_id: str) -> None:
        if neuron_id not in self._neuron_ids:
            self._neuron_ids.append(neuron_id)

    def register_file(self, path: str | Path) -> None:
        p = Path(path)
        if p not in self._file_paths:
            self._file_paths.append(p)

    def register_observation(self, obs_id: int) -> None:
        if obs_id not in self._observation_ids:
            self._observation_ids.append(obs_id)

    def discover_audit_artifacts(self, prefix: str = "AUDIT-") -> None:
        """Scan UMC + vault for artifacts matching *prefix*."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            for row in conn.execute(
                "SELECT id, source_file FROM neurons WHERE label LIKE ?",
                (f"%{prefix}%",),
            ):
                self.register_neuron(row["id"])
                sf = row["source_file"]
                if sf:
                    self.register_file(sf)
            for row in conn.execute(
                "SELECT id FROM observations WHERE content LIKE ?",
                (f"%{prefix}%",),
            ):
                self.register_observation(row["id"])
        finally:
            conn.close()
        if self.vault_root.exists():
            for md in self.vault_root.rglob(f"*{prefix}*.md"):
                self.register_file(md)

    def execute(self) -> dict:
        """Remove all registered artifacts. Returns summary dict."""
        summary = {
            "neurons_deleted": 0, "observations_deleted": 0,
            "synapses_deleted": 0, "fts_deleted": 0,
            "vectors_deleted": 0, "vector_metadata_deleted": 0,
            "vault_entries_deleted": 0, "files_deleted": 0,
            "integrity_ok": False, "fk_ok": False,
        }
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            conn.execute("BEGIN")
            for nid in self._neuron_ids:
                r = conn.execute("DELETE FROM synapses WHERE source_id=? OR target_id=?", (nid, nid))
                summary["synapses_deleted"] += r.rowcount
            for nid in self._neuron_ids:
                r = conn.execute("DELETE FROM observations WHERE neuron_id=?", (nid,))
                summary["observations_deleted"] += r.rowcount
            for oid in self._observation_ids:
                r = conn.execute("DELETE FROM observations WHERE id=?", (oid,))
                summary["observations_deleted"] += r.rowcount
            for nid in self._neuron_ids:
                for tbl, col in [("search_fts","neuron_id"),("search_vec","neuron_id")]:
                    try:
                        r = conn.execute(f"DELETE FROM {tbl} WHERE {col}=?", (nid,))
                        summary["fts_deleted" if "fts" in tbl else "vectors_deleted"] += r.rowcount
                    except sqlite3.OperationalError:
                        pass
            for nid in self._neuron_ids:
                r = conn.execute("DELETE FROM vector_metadata WHERE id=?", (str(nid),))
                summary["vector_metadata_deleted"] += r.rowcount
            for nid in self._neuron_ids:
                for child in ("causal_edges","ambiguities","knowledge_candidates"):
                    id_col = "cause_neuron_id" if child == "causal_edges" else "neuron_id"
                    try:
                        if child == "causal_edges":
                            conn.execute(f"DELETE FROM {child} WHERE cause_neuron_id=? OR effect_neuron_id=?", (nid, nid))
                        else:
                            conn.execute(f"DELETE FROM {child} WHERE {id_col}=?", (nid,))
                    except sqlite3.OperationalError:
                        pass
            for nid in self._neuron_ids:
                r = conn.execute("DELETE FROM vault WHERE id=?", (nid,))
                summary["vault_entries_deleted"] += r.rowcount
            for nid in self._neuron_ids:
                r = conn.execute("DELETE FROM neurons WHERE id=?", (nid,))
                summary["neurons_deleted"] += r.rowcount
            fk = conn.execute("PRAGMA foreign_key_check").fetchall()
            summary["fk_ok"] = len(fk) == 0
            integrity = conn.execute("PRAGMA integrity_check").fetchone()
            summary["integrity_ok"] = integrity[0] == "ok"
            if not summary["fk_ok"] or not summary["integrity_ok"]:
                conn.execute("ROLLBACK")
                summary["rolled_back"] = True
                return summary
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()
        for fp in self._file_paths:
            p = Path(fp)
            if p.exists():
                p.unlink()
                summary["files_deleted"] += 1
        return summary

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        try:
            self.execute()
        except Exception:
            pass
        return False
