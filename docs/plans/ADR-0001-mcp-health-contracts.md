# ADR-0001: MCP Registration and Post-Reboot Health Validation Contracts

- Status: Accepted
- Date: 2026-06-15
- Owners: Hive-Mind maintainers

## Context

The project depends on deterministic MCP registration across multiple agents and on a reproducible post-reboot validation flow. Prior behavior was partly implicit in scripts and tests, which increased regression risk during operational refactors.

## Decision

We define two explicit contracts.

### Contract A: MCP registration by agent

1. `scripts/register-mcp.sh` must register exactly three project-local servers:
- `sinapse-memory`
- `claude-mem-local`
- `neural-memory-local`

2. Contracted configuration roots:
- Default agents: `mcpServers`
- VS Code/Copilot: `servers` with `type: stdio`

3. Registration behavior:
- Preserve pre-existing third-party entries in target config files.
- Be idempotent when executed repeatedly.
- Keep Codex CLI parity between CLI registration and compatibility JSON.

### Contract B: post-reboot health validation

1. `scripts/validate_after_reboot.py` must fail fast when no real reboot is detected (`boot_id` unchanged).
2. Validation checks must include:
- service active state and restart count
- expected loopback-only ports
- UMC and claude-mem integrity
- smoke test result

3. claude-mem database selection must be deterministic:
- prefer project-local DB at `claude-mem/data/claude-mem.db`
- fallback to global `~/.claude-mem/claude-mem.db`

## Consequences

- Positive:
- Regressions in onboarding and health checks are caught by contract tests.
- Operational behavior is explicit and audit-friendly.
- Safer incremental refactors for plugin/runtime orchestration.

- Trade-offs:
- Slightly higher test maintenance burden when CLI interfaces evolve.
- Additional CI runtime for robustness tests.

## Rollback Plan

If regressions are observed:

1. Revert script changes impacting contract behavior.
2. Keep the new tests and mark affected checks as expected-fail only temporarily.
3. Restore the latest known-good configuration via backup files under `backups/`.

## Validation Metrics

Operational acceptance metrics after this ADR:

- MCP contract tests pass for codex, claude merge, and vscode root-key format.
- `validate_after_reboot` robustness tests pass under simulated edge conditions.
- No degradation in existing smoke, unit, integration, and e2e baseline.
