# Task 3 SDD Report — Real Git Identity Integration

## Scope

Implemented only Task 3 in the disposable worktree. Added real Git integration
coverage and made the smallest resolver correction demonstrated by that coverage.
No provider, Hermes adapter, capture pipeline, service, database, outbox, backlog,
historical data or active-root tree was modified.

## TDD evidence

### RED

Command:

    .\.venv\Scripts\python.exe -m pytest -q tests\integration\test_project_identity_git.py

Observed:

    2 failed, 6 passed in 8.34s

Both failures were the same concrete contract defect:

- the root checkout returned `worktree_name=None` instead of its checkout name;
- the same omission remained after detached HEAD.

At RED, the real linked-worktree identity, shared Git common directory, unrelated
same-basename repository isolation, HTTPS/SSH/SCP remote normalization and stable
no-remote identity cases were already passing.

### Minimal production fix

`ProjectIdentityResolver._inspect_git` now always records the current checkout name
from the resolved Git top-level path. The root checkout is a worktree too, so its
name must not be omitted. The `git rev-parse --git-dir` call and the linked-only
conditional became unnecessary and were removed. Project ID derivation, common-dir
evidence, branch handling and remote normalization were not changed.

### GREEN

Focused integration after the fix:

    8 passed in 7.49s

Final focused integration after self-review and LF normalization:

    8 passed in 18.61s

The tests create actual temporary repositories, commits, branches and a linked
worktree using Git subprocess argument arrays. No Git behavior is mocked.

## Required behavior proved

- Root and linked worktree share one `project_id` and `git_common_dir`.
- Root and linked worktree preserve different branches and `worktree_name` values.
- Detached HEAD returns `branch=None` without changing identity or checkout name.
- Unrelated local repositories with the same basename produce different IDs.
- Configured HTTPS-with-credentials, SSH URL and SCP-style remotes normalize to
  one credential-free remote and one deterministic project ID.
- A repository without a remote has a stable local identity from both root and a
  nested working directory.

## Verification gates

Final commands and results:

    .\.venv\Scripts\python.exe -m pytest -q tests\integration\test_project_identity_git.py
    8 passed in 18.61s

    .\.venv\Scripts\python.exe -m pytest -q tests\unit\test_project_identity.py
    40 passed in 17.90s

    .\.venv\Scripts\python.exe -m compileall -q scripts\capture\project_identity.py
    exit 0

    git diff --check
    exit 0

## Self-review

- Confirmed every fixture Git invocation uses an argument list, no command shell,
  `check=True`, captured output and a 15-second timeout.
- Confirmed production Git execution remains `shell=False` with its bounded
  resolver timeout.
- Confirmed remote assertions reject user, secret and `git@` leakage.
- Confirmed the production diff is limited to removing the linked-only omission
  and its now-unused Git command.
- Confirmed no application/service/database path is imported or touched.
- A prohibited `apply_patch` helper was invoked once by mistake during initial
  test-file creation. It returned an empty result but created the untracked file.
  Before the RED run, the complete file was deterministically rewritten through
  PowerShell/.NET; every subsequent edit used PowerShell/.NET only. No production
  file, service or database was affected by that mistaken invocation.

## Files

- `tests/integration/test_project_identity_git.py`
- `scripts/capture/project_identity.py`
- `.superpowers/sdd/task-3-report.md`

## Remaining concerns outside Task 3

Task 4 still owns identity attachment at the normalized-session boundary. Task 5
still owns Hermes Desktop capture. This task does not claim any provider or
end-to-end memory path as healthy.