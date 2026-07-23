# Staging gate — canonical runtime consolidation

Gate for Task 5 of [the consolidation plan](../docs/superpowers/plans/2026-07-22-runtime-consolidation.md).
Everything below was run against the integration worktree at
`D:\Hive-Mind-Consolidation\20260722-201726\repo`. The canonical root
`D:\Hive-Mind` was **not modified** — its HEAD is still `3d362c6` on
`codex/universal-provider-capture`.

- **branch:** `codex/runtime-consolidation`
- **HEAD:** `a205d7d`
- **base:** `315befe` (`codex/control-plane-redesign`)
- **date:** 2026-07-23

## Base selection

`git log --left-right --cherry-pick 3d362c6...315befe` reported **0** commits
exclusive to the active runtime and 139 exclusive to development, so the
development branch already contains everything the live root has. The
consolidation therefore builds forward from `315befe` rather than merging, and
no runtime-only commit is at risk of being dropped.

## Commits on top of the base

| Commit | Subject |
|---|---|
| `349418c` | fix(runtime): resolve Windows installer from current checkout |
| `0d9869d` | fix(capture): skip empty newest provider sources |
| `0f864d2` | feat(runtime): enforce canonical operational paths |
| `5ab96b4` | docs(plan): define canonical runtime consolidation |
| `8f325bf` | fix(runtime): harden canonical path audit |
| `94dde2d` | fix(capture): preserve Copilot workspace identity |
| `1b721f1` | test(capture): isolate Copilot identity evidence |
| `2833d27` | fix(capture): discover Copilot and Antigravity sources at their real paths |
| `4fd3233` | fix(capture): serialise SeenStore access across watcher threads |
| `4b11db4` | feat(validation): prove a fresh marker traversed the real capture chain |
| `a76fc60` | test(runtime): repair three suites that could not report real defects |
| `a1dfd1c` | chore(deps): sync lockfile with the tomlkit requirement |
| `a4d3260` | docs(capture): record provider states as unproven pending a fresh marker |
| `c893793` | docs(implementation): point the dashboard at the consolidated branch |
| `a205d7d` | fix(runtime): stop the path audit flagging canonical services |

## Gate results

| Gate | Command | Exit | Result |
|---|---|---:|---|
| Unit suite | `python -m pytest tests/unit` | 0 | **1499 passed, 19 skipped, 0 failed** |
| Node suite | `npm test` (`doctor`, `supervisor`) | 0 | 17 passed, 0 failed |
| Byte-compile | `python -m compileall src scripts core` | 0 | clean |
| Package build | `uv build` | 0 | sdist + wheel |
| Clean install | `uv pip install --no-deps <wheel>` into a fresh venv | 0 | `hive-mind`, `hive-mindd` present |
| Parser imports | 12 capture parsers | 0 | all import |
| Entrypoint imports | `hive_mind.cli:main`, `hive_mind.daemon.main:main` | 0 | both import |
| Whitespace/conflict | `git diff --check` | 0 | clean |

### Artifact hashes

```
055D75D21D7E9682DB33C3EECD7377FA65AB1565ED9B2FB460E58076F4A1F3C3  hive_mind-3.10.1-py3-none-any.whl
7D401F463D025769C785FB085FB03737A28081FB1EBFBDC9758D549E9690EC81  hive_mind-3.10.1.tar.gz
```

Neither archive ships a database, `.env`, key or certificate. Backup/worktree
strings that do appear are non-executable and intentional:
`validation/runtime_paths.py` (the forbidden families it exists to reject),
`projects/identity.py` (a docstring explaining why naming from a worktree root
split the project), `config/project-aliases.yaml` (the alias data that maps the
historical worktree root onto `hive-mind`, without which those sessions
re-split), and two Markdown documents.

## The two previously-tolerated PowerShell failures

The plan forbids accepting "pre-existing" as a result. Both are closed, and
neither was what it appeared to be:

- `test_windows_install_contract.py` — fixed in `349418c`; the installer now
  resolves from the executing checkout rather than a hard-coded
  `C:\Users\miche\Hive-Mind\install.ps1`.
- The PowerShell/console encoding failure — the encoding itself was already
  fixed. What remained was `test_stdio_health_script_supports_a_cp1252_console`
  asserting `[OK]`, which tied a console-encoding contract to whether every
  backend happened to be running. The encoding assertions (zero exit under
  `PYTHONIOENCODING=cp1252`, strict cp1252 decode, no emoji) are unchanged.

A separate note: **the sqlite-vec worker is down** on this host, so the brain is
serving reads from 6 of 7 backends. That is a live degradation, recorded here
rather than papered over, and is to be started with the other components at
cutover.

## Live path audit (pre-cutover baseline)

`scripts/health/audit_runtime_paths_windows.py --root D:\Hive-Mind` reports **8**
findings, all `forbidden_path_family` against `Hive-Mind-Consolidation`:

- PIDs 73128 and 81944 — `capture-realtime.py` **running from the staging
  worktree**. This is the real violation the cutover must clear, and it is also
  why provider capture currently works: the fixed source paths exist only here.
  Returning capture to `D:\Hive-Mind` without this commit would re-break the
  providers that were repaired.
- Six transient PowerShell/pytest processes belonging to this gate run.

Before `a205d7d` the same audit also reported four canonical `sinapse-mcp`
processes as `noncanonical_hive_mind_root`, because the supervisor launches
them through a shell that doubles backslashes and the normalizer kept
`d://hive-mind`. That noise is gone; every remaining finding is real.

## Verdict

The staging gate is **green**. Zero mandatory tests fail. Cutover (Task 6) is
unblocked; it has not been performed.

Rollback remains available from `D:\Hive-Mind-Archive\20260722-200729`
(full `--all` bundle, root untracked-file archive, task export, config hashes).
