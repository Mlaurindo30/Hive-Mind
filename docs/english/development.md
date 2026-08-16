# Development

How to change Hive-Mind, test, build, and publish releases.

Target audience: those who contribute code or documentation.

---

## How to make changes

1. **Consult before acting.** Read the project's current state (`sinapse_query`,
   or ) before touching something that may already
   have a recorded decision.
2. **Locate the owner of the area.** Each area has a single owner — see the
   [change → documentation](#change--documentation) matrix.
3. **Make the code change first**, then the documentation, **in the same
   delivery**. New behavior without an updated document is not ready
   (maintenance rule 7 — see [README.md](README.md#maintenance-rules)).
4. **Run the tests** of the corresponding layer before declaring it done
   (see [Tests](#tests)).
5. **Record what is reusable** (decision or learning) in the brain, with
   evidence of what was verified.

---

## Change → documentation matrix

| Change | Mandatory documentation |
|---|---|
| Native `hive-mind` CLI | [cli.md](cli.md), [README.md](README.md) |
| MCP agent registration | [agents.md](agents.md) |
| Capture provider / project identity | [capture.md](capture.md), [capture/providers.md](capture/providers.md) |
| Daemon / service manifest | [runtime.md](runtime.md), operations runbook |
| Database / schema | [data-pipeline.md](data-pipeline.md), migration notes |
| AI models / Model Gateway | [ai-models.md](ai-models.md), [ai-models.md](ai-models.md) |
| Dream Cycle | [data-pipeline.md](data-pipeline.md) |
| Installation | [installation.md](installation.md) (and per-platform variants) |
| Health / doctor / observability | [observability.md](observability.md) |
| Security | [security.md](security.md) |
| Release | [CHANGELOG.md](../CHANGELOG.md), release notes |

Every delivery that changes behavior in one of these areas can only be
considered complete with the corresponding documentation updated in the same
delivery.

---

## Tests

Before any commit:

```bash
./tests/run_all.sh                    # full suite (Smoke → Unit → Integration → E2E)
bash tests/smoke/test_smoke.sh        # minimum acceptable if the suite is long
```

| Level | Command | Requirements | Note |
|---|---|---|---|
| Smoke | `bash tests/smoke/test_smoke.sh` | binaries on PATH | quick diagnosis (< 5 min) |
| Unit | `uv run pytest tests/unit/ -v` | pytest, Python 3.12 | mocks; **does not call a real LLM** |
| Integration | `HIVE_RUN_INTEGRATION=1 uv run pytest tests/integration/ -v` | real backends | explicit gate via env |
| E2E | `uv run pytest tests/e2e/ -v` | full system | complete session cycle |
| Real (K9) | `./tests/run_real_knowledge.sh` | real environment | separate knowledge suite |
| npm | `npm test` (in `npm/`) | Node 18+ | `node --test test/doctor.test.js test/supervisor.test.js` |

- **Unit does not call a real LLM.** The logic around the LLM is tested with
  deterministic data; the real model only enters in `tests/test_synthesis.py`
  and the E2E flows.
- **Test count:** the suite grows fast — do not treat a fixed number as a
  target. Measure with
  `rg -n "^\s*(async\s+def|def)\s+test_" tests | wc -l` (functions) and
  `rg -l "^\s*(async\s+def|def)\s+test_" tests | wc -l` (files).
- **Named "service-offline" skips** indicate a `degraded` state, not full
  success.

### CI contracts

- `python scripts/release/validate_package.py --source-root .` validates the
  release version contract (see [Release](#release)) — runs in the Windows
  workflow (`.github/workflows/test-windows.yml`).
- Docker restart policy contract:
  `tests/unit/test_compose_restart_policy.py` fails if any mandatory compose
  service does not declare `restart: unless-stopped`.

---

## Build

The project is a Python package managed by `uv` + `hatchling`, with a separate
npm package in `npm/`.

```bash
uv sync                      # reproducible environment (.venv + uv.lock), includes dev group
uv sync --extra reranker     # + optional cross-encoder reranker dependency
uv build                     # generates sdist + wheel in dist/
```

- Python: `>=3.12,<3.13` (defined in `pyproject.toml`).
- The package exposes the `hive-mind` (`hive_mind.cli:main`) and `hive-mindd`
  (`hive_mind.daemon.main:main`) entrypoints, plus the Windows gui-scripts.
- The wheel build includes resources (`src/hive_mind/resources/`) and
  **excludes** secrets and state: `.env`, `.env.*`, `*.secret`, `hive_mind.db`,
  `hive_mind.db-*`, `logs/`, `backups/`, `config/keys/` (see `[tool.hatch.build]`).

---

## Release

The version contract requires that **seven locations** agree on the same
semantic version and that it **does not regress** below the latest git tag. The
validator is `scripts/release/validate_package.py`.

| Location | Field |
|---|---|
| `pyproject.toml` | `[project] version` |
| `npm/package.json` | `version` |
| `core/version.py` | `__version__` |
| `scripts/services/sinapse-api.py` | `version="..."` |
| `scripts/services/sinapse_mcp.py` | `"serverInfo": {..., "version": "..."}` |
| `core/telemetry.py` | `"service.version": "..."` |
| `CHANGELOG.md` | `## Unreleased ... vX.Y.Z` |

Release sequence:

1. **Version bump** in the seven locations above, all to the same version.
2. **Changelog**: write the `## Unreleased ... vX.Y.Z` entry at the top of
   [`CHANGELOG.md`](../CHANGELOG.md), in the `Added` / `Changed` / `Fixed`
   sections.
3. **Validate the contract**:
   ```bash
   python scripts/release/validate_package.py --source-root .
   ```
   (exits 0 if everything agrees and the version does not regress; otherwise
   lists each location and the divergence.)
4. **Tag**:
   ```bash
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```
5. **GitHub Release**: `gh release create vX.Y.Z` with the release notes
   derived from the changelog.
6. **Separate npm publish**: the `hive-sinapse-mind` package lives in `npm/` and
   is published independently:
   ```bash
   cd npm && npm publish
   ```

The npm is a **distinct** package (`hive-sinapse-mind`, Node ≥ 18, entrypoint
`bin/hive-mind.js`) — versioned together with Python by the contract above, but
published separately.

---

## Boundaries

Never commit, **under any circumstances**:

- `.env` — API keys, tokens, OAuth secrets.
- `hive_mind.db` — personal memory (the whole database, including the table of
  encrypted secrets).
- `~/.claude-mem/` and `claude-mem/data/lightrag/` — observations and
  embeddings.
- `backups/` — UMC backups.
- `*.secret`, `config/keys/**` — credentials.
- `logs/` and `dist/` — local artifacts.

`.gitignore` covers `.env` and `*.db`; `[tool.hatch.build]` excludes the same
from the wheel/sdist. Additional guardrails in [AGENTS.md](../AGENTS.md) (root):

- never modify `cerebro/` without the Watcher active (or run
  `./scripts/graph/build-graph.sh` afterwards);
- never duplicate data between the vault and the external tools — the vault is
  the single source;
- never hardcode LLM models — the system obeys `HIVE_*_PROVIDER/MODEL` from
  `.env`;
- new code that creates/modifies a vault file **must** use the constants from
  `core/paths.py`, not hardcoded paths.

Related:

- [README.md](README.md) — index and maintenance rules
- [cli.md](cli.md) — the native CLI and its subgroups
- [capture.md](capture.md) — tests that protect the canonical identity
- [runtime.md](runtime.md) — manifest and daemon
-  — current state by phase
