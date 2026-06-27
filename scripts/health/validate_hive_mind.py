#!/usr/bin/env python3
import sys
import os
import json
import sqlite3
from pathlib import Path

# Configura paths
SINAPSE_HOME = os.environ.get("SINAPSE_HOME", str(Path(__file__).resolve().parent.parent.parent))
sys.path.append(SINAPSE_HOME)
DB_PATH = os.path.join(SINAPSE_HOME, "hive_mind.db")

from core.database import get_connection, query_hybrid

def test_1_database_foundation():
    print("Test 1: Database Foundation & sqlite-vec...")
    try:
        conn = get_connection()
        cursor = conn.execute("SELECT vec_version();")
        version = cursor.fetchone()[0]
        print(f"  [OK] sqlite-vec version: {version}")
        
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        table_names = [t[0] for t in tables]
        required = ['neurons', 'synapses', 'observations', 'search_vec']
        for r in required:
            if r in table_names:
                print(f"  [OK] Table '{r}' exists.")
            else:
                raise Exception(f"Missing table: {r}")
        conn.close()
        return True
    except Exception as e:
        print(f"  [FAIL] Database foundation: {e}")
        return False

def test_2_graphify_sync():
    print("Test 2: Graphify Structural Sync...")
    try:
        conn = get_connection()
        n_count = conn.execute("SELECT count(*) FROM neurons").fetchone()[0]
        s_count = conn.execute("SELECT count(*) FROM synapses").fetchone()[0]
        v_count = conn.execute("SELECT count(*) FROM search_vec").fetchone()[0]
        print(f"  [INFO] Neurons: {n_count}, Synapses: {s_count}, Vectors: {v_count}")
        if n_count > 0 and s_count > 0:
            print("  [OK] Structural data present.")
            return True
        else:
            print("  [FAIL] Database is empty. Run graphify update first.")
            return False
    except Exception as e:
        print(f"  [FAIL] Graphify sync: {e}")
        return False

def test_3_hybrid_search_mcp():
    print("Test 3: Hybrid Search (RRF) & MCP...")
    try:
        query = "sinapse"
        results = query_hybrid(query, limit=3)
        if len(results) > 0:
            print(f"  [OK] Hybrid search returned {len(results)} results for '{query}'.")
            print(f"  [OK] Top hit: {results[0]['label']}")
            return True
        else:
            print("  [FAIL] Hybrid search returned no results.")
            return False
    except Exception as e:
        print(f"  [FAIL] Hybrid search: {e}")
        return False

def test_4_persistence_dashboard():
    print("Test 4: Persistence & Dashboard Integration...")
    try:
        # Adapter import-safe do plugin Hermes (registra sys.modules["sinapse_memory"]).
        from plugins.hermes import sinapse_memory as sm

        test_title = "Test Decision 2026"
        test_content = "Verification of Phase 4 Dashboard integration."
        success = sm._umc_save_observation(test_title, test_content, obs_type="decision")
        
        if success:
            conn = get_connection()
            obs = conn.execute("SELECT * FROM observations WHERE title = ?", (test_title,)).fetchone()
            conn.close()
            if obs:
                print("  [OK] Observation persisted in UMC.")
                return True
        print("  [FAIL] Persistence failed.")
        return False
    except Exception as e:
        print(f"  [FAIL] Persistence test: {e}")
        return False

def main():
    print("=== HIVE-MIND VALIDATION SUITE (PHASES 1-4) ===")
    results = [
        test_1_database_foundation(),
        test_2_graphify_sync(),
        test_3_hybrid_search_mcp(),
        test_4_persistence_dashboard()
    ]
    
    print("=" * 45)
    if all(results):
        print("RESULT: ALL TESTS PASSED! Ready for Phase 5.")
        sys.exit(0)
    else:
        print("RESULT: SOME TESTS FAILED. Check the logs above.")
        sys.exit(1)

if __name__ == "__main__":
    main()
