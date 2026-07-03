"""Helper for tests/real/test_disaster_recovery.py.

Loads sqlite-vec on the recovery copy of hive_mind.db and prints
row counts for search_vec and search_fts.
"""

from __future__ import annotations

import sqlite3
import sys


def main(db_path: str) -> int:
    conn = sqlite3.connect(db_path)
    conn.enable_load_extension(True)
    try:
        import sqlite_vec
        sqlite_vec.load(conn)
    except Exception as e:
        print(f"no-vec: {e}")
        return 0
    vec = conn.execute("SELECT COUNT(*) FROM search_vec").fetchone()[0]
    fts = conn.execute("SELECT COUNT(*) FROM search_fts").fetchone()[0]
    print(f"vec {vec} fts {fts}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "hive_mind.db"))
