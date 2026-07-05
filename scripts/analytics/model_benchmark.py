#!/usr/bin/env python3
"""
scripts/analytics/model_benchmark.py — CLI for the Model Gateway (Priority 1).

Usage:
    python scripts/analytics/model_benchmark.py --list
    python scripts/analytics/model_benchmark.py --health
    python scripts/analytics/model_benchmark.py --role validator --prompt "Responda em JSON" --schema tests/fixtures/simple_schema.json
    python scripts/analytics/model_benchmark.py --all --output logs/model-benchmark.json
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.model_gateway import ModelGateway  # noqa: E402
from core.model_registry import ModelProfile  # noqa: E402

_BENCH_SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
_BENCH_PROMPT = 'Reply with exactly this JSON object and nothing else: {"ok": true}'
_BENCH_ATTEMPTS = 3


def cmd_list(gateway: ModelGateway) -> int:
    rows = []
    for p in gateway.registry.list_models():
        rows.append({
            "id": p.id, "provider": p.provider, "enabled": p.enabled,
            "roles": p.roles, "cost_mode": p.cost_mode, "priority": p.priority,
            "capabilities": dataclasses.asdict(p.capabilities),
        })
    print(json.dumps(rows, indent=2, ensure_ascii=False))
    return 0


def cmd_health(gateway: ModelGateway) -> int:
    print(json.dumps(gateway.health(), indent=2, ensure_ascii=False))
    return 0


def cmd_single(gateway: ModelGateway, role: Optional[str], prompt: str, schema_path: Optional[str]) -> int:
    messages = [{"role": "user", "content": prompt}]
    if schema_path:
        schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
        resp = gateway.structured(messages, schema, role=role)
    else:
        resp = gateway.chat(messages, role=role)
    print(json.dumps({
        "ok": resp.ok, "content": resp.content, "model_id": resp.model_id,
        "provider": resp.provider, "latency_ms": round(resp.latency_ms, 2),
        "fallback_used": resp.fallback_used, "fallback_chain": resp.fallback_chain,
        "error": resp.error,
    }, indent=2, ensure_ascii=False, default=str))
    return 0 if resp.ok else 1


def _benchmark_profile(gateway: ModelGateway, profile: ModelProfile) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "model_id": profile.id, "provider": profile.provider,
        "success_rate": None, "json_valid_rate": None, "schema_valid_rate": None,
        "tool_call_valid_rate": None, "latency_p50": None, "latency_p95": None,
        "tokens_per_second": None, "cost_estimate": None, "fallback_rate": None,
        "error_rate": None,
    }
    if not profile.capabilities.structured_output:
        metrics["error_rate"] = None
        metrics["success_rate"] = None
        return metrics  # not applicable — never fabricate 0/1 (Requirement 29)

    latencies: list[float] = []
    successes = 0
    fallback_count = 0
    output_tokens_total = 0
    time_s_total = 0.0
    cost_total = 0.0
    cost_seen = False

    for _ in range(_BENCH_ATTEMPTS):
        resp = gateway.structured(
            [{"role": "user", "content": _BENCH_PROMPT}], _BENCH_SCHEMA, model_id=profile.id,
        )
        latencies.append(resp.latency_ms)
        if resp.ok:
            successes += 1
        if resp.fallback_used:
            fallback_count += 1
        if resp.output_tokens:
            output_tokens_total += resp.output_tokens
            time_s_total += resp.latency_ms / 1000.0
        if resp.cost_estimate is not None:
            cost_total += resp.cost_estimate
            cost_seen = True

    metrics["success_rate"] = successes / _BENCH_ATTEMPTS
    metrics["json_valid_rate"] = successes / _BENCH_ATTEMPTS
    metrics["schema_valid_rate"] = successes / _BENCH_ATTEMPTS
    metrics["error_rate"] = 1 - (successes / _BENCH_ATTEMPTS)
    metrics["fallback_rate"] = fallback_count / _BENCH_ATTEMPTS
    if latencies:
        ordered = sorted(latencies)
        metrics["latency_p50"] = round(ordered[len(ordered) // 2], 2)
        metrics["latency_p95"] = round(ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))], 2)
    if time_s_total > 0:
        metrics["tokens_per_second"] = round(output_tokens_total / time_s_total, 2)
    if cost_seen:
        metrics["cost_estimate"] = round(cost_total / _BENCH_ATTEMPTS, 6)
    if not profile.capabilities.tool_calling:
        metrics["tool_call_valid_rate"] = None  # capability doesn't apply (Requirement 29)
    return metrics


def cmd_all(gateway: ModelGateway, output_path: str) -> int:
    results = []
    skipped = []
    for profile in gateway.registry.list_models():
        if not profile.enabled:
            skipped.append({"model_id": profile.id, "reason": "disabled"})
            continue
        results.append(_benchmark_profile(gateway, profile))
    report = {"models_benchmarked": len(results), "models_skipped": skipped, "results": results}
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Model Gateway (Priority 1) inspection/benchmark CLI")
    parser.add_argument("--list", action="store_true", help="print all configured model profiles")
    parser.add_argument("--health", action="store_true", help="print ModelGateway.health() as JSON")
    parser.add_argument("--role", help="role to select a model by (single ad-hoc call)")
    parser.add_argument("--prompt", help="prompt for a single ad-hoc call")
    parser.add_argument("--schema", help="JSON Schema path; makes the ad-hoc call structured")
    parser.add_argument("--all", action="store_true", help="run the fixed benchmark battery on every enabled model")
    parser.add_argument("--output", default="logs/model-benchmark.json", help="report path for --all")
    args = parser.parse_args()

    gateway = ModelGateway.from_config()

    if args.list:
        return cmd_list(gateway)
    if args.health:
        return cmd_health(gateway)
    if args.all:
        return cmd_all(gateway, args.output)
    if args.role and args.prompt:
        return cmd_single(gateway, args.role, args.prompt, args.schema)

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
