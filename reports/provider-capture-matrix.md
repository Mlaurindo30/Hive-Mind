# Provider capture evidence matrix (D004-M correction)

Staging HEAD `1b721f1` · 2026-07-22

This matrix separates three facts that must not be collapsed into one status:

- `HISTORICALLY_PROVEN`: a real provider event was previously observed beyond
  provider invocation. It is evidence of prior operation, not a fresh pass on
  this staging HEAD.
- `SOURCE_PARSES_NOW`: the current staging adapter finds and parses a real local
  provider source. It proves source compatibility, not delivery through the
  whole chain.
- `FRESH_CHAIN_PENDING`: no new marker has yet been followed on this staging
  HEAD through source, parser, ingest, Claude Mem, bridge, UMC and dedupe.

The regression is in Hive-Mind code/configuration: the live runtime loaded an
old `capture_adapters.py` whose source paths pointed at locations abandoned by
the providers. It is not a provider limitation, missing deployment requirement,
login conclusion or evidence that an IDE/CLI cannot be automated.

## Evidence matrix

| Provider | Lane | Historical evidence | Current staging source | Fresh chain | Evidence boundary |
|---|---|---|---|---|---|
| claude | native | `HISTORICALLY_PROVEN` | native lane | `FRESH_CHAIN_PENDING` | Claude Mem native capture operated previously; universal adapter parsing does not apply |
| codex | universal | `HISTORICALLY_PROVEN` | not re-measured in this correction | `FRESH_CHAIN_PENDING` | prior real automated end-to-end evidence remains historical until a post-staging marker is traced |
| qwen | universal | `HISTORICALLY_PROVEN` | `SOURCE_PARSES_NOW` | `FRESH_CHAIN_PENDING` | current staging parses the real source; the prior complete canary is not a fresh staging pass |
| antigravity | universal | `HISTORICALLY_PROVEN` | `SOURCE_PARSES_NOW` | `FRESH_CHAIN_PENDING` | real IDE marker was captured previously; staging now finds/parses the real Antigravity source |
| copilot | universal | `HISTORICALLY_PROVEN` | `SOURCE_PARSES_NOW` | `FRESH_CHAIN_PENDING` | real headless invocation exited 0 and real SQLite sources exist; staging parses them |
| hermes | universal | `HISTORICALLY_PROVEN` | `SOURCE_PARSES_NOW` | `FRESH_CHAIN_PENDING` | real markers/ACKs were persisted in `AppData/Local/hermes/state.db`; staging parses that source |
| kilo | universal | invocation proven (`exit 0`) | `SOURCE_PARSES_NOW` | `FRESH_CHAIN_PENDING` | headless provider invocation succeeded, but the old Hive-Mind capture chain failed after invocation |
| mimo | universal | invocation proven (`exit 0`) | `SOURCE_PARSES_NOW` | `FRESH_CHAIN_PENDING` | headless provider invocation succeeded, but the old Hive-Mind capture chain failed after invocation |
| kimi | universal | real source previously observed | `SOURCE_PARSES_NOW` | `FRESH_CHAIN_PENDING` | real `wire.jsonl` exists and the current parser reads it; no login/model conclusion is inferred |

No row above is a fresh end-to-end `PASS`. A fresh provider marker is required
before promotion from `FRESH_CHAIN_PENDING`.

## Registration-only integrations

`cursor`, `gemini`, `kiro`, `opencode` and `vscode` are MCP registration
targets in the current architecture. That classification does not assert that
their products are non-operational; it only says this matrix has no universal
capture adapter evidence for them yet.

## Corrected gate policy

| Evidence | Meaning |
|---|---|
| `HISTORICALLY_PROVEN` | real prior operation; may establish the expected baseline |
| `SOURCE_PARSES_NOW` | current adapter compatibility with a real local source |
| `FRESH_CHAIN_PENDING` | operational gate remains open on this HEAD |
| `FRESH_CHAIN_PROVEN` | a new marker traversed the complete chain on this HEAD |

Provider invocation and source parsing are necessary evidence, but neither is
equivalent to complete capture. Conversely, failure to complete a canary while
Hive-Mind watches obsolete paths is a Hive-Mind regression, not
`BLOCKED_BY_PROVIDER`, `NOT_CONFIGURED`, `OK_EXTERNAL` or `OK_NOT_REQUIRED`.

## Hive-Mind regression and restoration boundary

The current staging adapters find and parse real sources for Antigravity,
Copilot, Hermes, Kilo, Kimi, MiMo and Qwen. This repairs the known source-path
compatibility defect in code. The delivery is still open until fresh markers
prove ingest, Claude Mem correlation, bridge, canonical workspace identity,
UMC persistence and dedupe for each required provider.
