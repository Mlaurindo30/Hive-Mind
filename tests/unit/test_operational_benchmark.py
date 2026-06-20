from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "operational_benchmark", ROOT / "scripts" / "analytics" / "operational_benchmark.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_percentile_handles_bounds_and_empty():
    assert MODULE.percentile([], 95) is None
    assert MODULE.percentile([10, 20, 30], 0) == 10
    assert MODULE.percentile([10, 20, 30], 100) == 30


def test_measure_hybrid_query_uses_reported_latency():
    def fake_query(_query):
        return {"query_latency_ms": 42.0}

    result = MODULE.measure_hybrid_query_p95(fake_query, "health", iterations=5)
    assert result["samples"] == 5
    assert result["p95_ms"] == 42.0


def test_daily_quarantine_rate_from_sqlite(tmp_path):
    db = tmp_path / "hive_mind.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE observations(id INTEGER PRIMARY KEY, archived INTEGER, created_at TEXT)")
    conn.execute("INSERT INTO observations(archived, created_at) VALUES (2, datetime('now'))")
    conn.execute("INSERT INTO observations(archived, created_at) VALUES (1, datetime('now'))")
    conn.commit()
    conn.close()

    result = MODULE.daily_quarantine_rate(db)
    assert result["observations_24h"] == 2
    assert result["quarantined_24h"] == 1
    assert result["rate"] == 0.5


def test_evaluate_slos_detects_violations():
    metrics = {
        "hybrid_query": {"p95_ms": 3500.0},   # above 3000ms threshold
        "write_to_index": {"found": False, "elapsed_s": 1.0},
        "quarantine": {"rate": 0.01},
    }
    checks = MODULE.evaluate_slos(metrics, MODULE.DEFAULT_SLOS)
    assert checks["hybrid_query_p95_ms"] is False
    assert checks["write_to_index_cycle_s"] is False
    assert checks["daily_quarantine_rate"] is True


def test_main_carrega_backend_sinapse_memory(monkeypatch, tmp_path):
    db = tmp_path / "hive_mind.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE observations(id INTEGER PRIMARY KEY, archived INTEGER, created_at TEXT)")
    conn.commit()
    conn.close()

    monkeypatch.setattr(MODULE, "DB_PATH", db)
    monkeypatch.setattr(MODULE, "VAULT_DIR", tmp_path / "vault")
    monkeypatch.setattr(MODULE, "METRICS_DIR", tmp_path / "metrics")
    monkeypatch.delitem(sys.modules, "sinapse_memory", raising=False)
    monkeypatch.setattr(
        MODULE,
        "measure_hybrid_query_p95",
        lambda query_fn, query, iterations: {"samples": iterations, "latencies_ms": [1.0], "p95_ms": 1.0},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["operational_benchmark.py", "--iterations", "1", "--timeout", "0.01", "--no-fail"],
    )
    assert MODULE.main() == 0
