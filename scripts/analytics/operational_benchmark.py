#!/usr/bin/env python3
"""Continuous operational benchmark with SLO evaluation.

SLOs tracked:
- Hybrid query p95 latency (ms)
- Write-to-index cycle time (s)
- Daily quarantine rate
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent.parent
# Bootstrap: raiz no sys.path para `from plugins.hermes ...` quando rodado direto.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DB_PATH = ROOT / "hive_mind.db"
VAULT_DIR = ROOT / "cerebro"
METRICS_DIR = ROOT / "logs" / "metrics"

DEFAULT_SLOS = {
    # fastembed local + vector scan over 20k+ rows: measured ~2400ms p95
    "hybrid_query_p95_ms": 3000.0,
    # graphify debounce (2s) + rebuild (5-7s) + UMC neuron+synapse sync (~25s) = ~35s
    "write_to_index_cycle_s": 60.0,
    "daily_quarantine_rate": 0.05,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def percentile(values: List[float], p: float) -> Optional[float]:
    if not values:
        return None
    if p <= 0:
        return min(values)
    if p >= 100:
        return max(values)
    ordered = sorted(values)
    index = int(round((len(ordered) - 1) * (p / 100.0)))
    return float(ordered[index])


def measure_hybrid_query_p95(
    query_fn: Callable[[str], Optional[Dict[str, object]]],
    query: str,
    iterations: int,
) -> Dict[str, object]:
    latencies: List[float] = []
    for _ in range(max(1, iterations)):
        t0 = time.perf_counter()
        result = query_fn(query)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        if isinstance(result, dict) and isinstance(result.get("query_latency_ms"), (int, float)):
            latencies.append(float(result["query_latency_ms"]))
        else:
            latencies.append(elapsed_ms)

    p95 = percentile(latencies, 95)
    return {
        "samples": len(latencies),
        "latencies_ms": [round(v, 3) for v in latencies],
        "p95_ms": round(p95, 3) if p95 is not None else None,
    }


def measure_write_to_index_cycle(
    db_path: Path,
    vault_dir: Path,
    timeout_s: float = 60.0,
    poll_s: float = 0.5,
) -> Dict[str, object]:
    marker = f"SLO-BENCH-{uuid.uuid4().hex[:10]}"
    bench_file = vault_dir / "Bench-Test.md"
    bench_file.parent.mkdir(parents=True, exist_ok=True)

    with open(bench_file, "a", encoding="utf-8") as f:
        f.write(f"\n\nBenchmark marker: {marker}\n")

    started = time.perf_counter()
    found = False
    attempts = 0
    while (time.perf_counter() - started) <= timeout_s:
        attempts += 1
        try:
            conn = sqlite3.connect(db_path)
            row = conn.execute(
                "SELECT 1 FROM neurons WHERE content LIKE ? LIMIT 1",
                (f"%{marker}%",),
            ).fetchone()
            conn.close()
            if row:
                found = True
                break
        except sqlite3.Error:
            pass
        time.sleep(poll_s)

    elapsed_s = time.perf_counter() - started
    return {
        "marker": marker,
        "found": found,
        "attempts": attempts,
        "elapsed_s": round(elapsed_s, 3),
        "timeout_s": timeout_s,
    }


def daily_quarantine_rate(db_path: Path) -> Dict[str, object]:
    conn = sqlite3.connect(db_path)
    try:
        total = conn.execute(
            "SELECT COUNT(*) FROM observations WHERE datetime(created_at) >= datetime('now', '-1 day')"
        ).fetchone()[0]
        quarantined = conn.execute(
            "SELECT COUNT(*) FROM observations WHERE archived = 2 AND datetime(created_at) >= datetime('now', '-1 day')"
        ).fetchone()[0]
    finally:
        conn.close()

    rate = (quarantined / total) if total else 0.0
    return {
        "observations_24h": total,
        "quarantined_24h": quarantined,
        "rate": round(rate, 6),
    }


def evaluate_slos(metrics: Dict[str, object], thresholds: Dict[str, float]) -> Dict[str, bool]:
    hybrid = metrics.get("hybrid_query", {})
    write_cycle = metrics.get("write_to_index", {})
    quarantine = metrics.get("quarantine", {})

    hybrid_p95 = hybrid.get("p95_ms")
    write_elapsed = write_cycle.get("elapsed_s") if write_cycle.get("found") else None
    quarantine_rate = quarantine.get("rate")

    checks = {
        "hybrid_query_p95_ms": (
            isinstance(hybrid_p95, (int, float)) and hybrid_p95 <= thresholds["hybrid_query_p95_ms"]
        ),
        "write_to_index_cycle_s": (
            isinstance(write_elapsed, (int, float)) and write_elapsed <= thresholds["write_to_index_cycle_s"]
        ),
        "daily_quarantine_rate": (
            isinstance(quarantine_rate, (int, float)) and quarantine_rate <= thresholds["daily_quarantine_rate"]
        ),
    }
    return checks


def load_query_backend():
    # Adapter import-safe do plugin Hermes (registra sys.modules["sinapse_memory"]).
    from plugins.hermes import sinapse_memory as sm
    return sm._query_vault_knowledge


def persist_report(payload: Dict[str, object]) -> None:
    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    latest = METRICS_DIR / "operational_slo_latest.json"
    history = METRICS_DIR / f"operational_slo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    serialized = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    latest.write_text(serialized, encoding="utf-8")
    history.write_text(serialized, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", default="health")
    parser.add_argument("--iterations", type=int, default=15)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--no-fail", action="store_true")
    args = parser.parse_args()

    _query_vault_knowledge = load_query_backend()

    metrics = {
        "hybrid_query": measure_hybrid_query_p95(
            query_fn=lambda q: _query_vault_knowledge(q),
            query=args.query,
            iterations=args.iterations,
        ),
        "write_to_index": measure_write_to_index_cycle(
            db_path=DB_PATH,
            vault_dir=VAULT_DIR,
            timeout_s=args.timeout,
        ),
        "quarantine": daily_quarantine_rate(DB_PATH),
    }

    checks = evaluate_slos(metrics, DEFAULT_SLOS)
    payload = {
        "captured_at": utc_now(),
        "thresholds": DEFAULT_SLOS,
        "checks": checks,
        "metrics": metrics,
        "status": "pass" if all(checks.values()) else "fail",
    }
    persist_report(payload)
    print(json.dumps(payload, indent=2, ensure_ascii=False))

    if args.no_fail:
        return 0
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
