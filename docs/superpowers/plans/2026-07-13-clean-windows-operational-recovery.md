# Clean Windows Operational Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a clean native Windows `local-full` install operational, or fail with exact diagnostics before it claims success.

**Architecture:** `install.ps1` orchestrates profile-aware prerequisite, Docker, compose and supervisor readiness. The service manifest is the shared contract for installer, supervisor and post-reboot doctor. Tests isolate host-state paths and prove the failure boundary before implementation.

**Tech Stack:** PowerShell 7, Python 3.12/pytest, Node 20 `node:test`, Docker Compose, Task Scheduler, GitHub Actions Windows.

## Global Constraints

- Never reuse `.env`, `cerebro/`, `hive_mind.db`, Docker volumes or global Claude Mem data in clean-install tests.
- `local-min` does not require Docker; `local-full` requires Docker, Milvus, RAGFlow, FalkorDB and Syncthing readiness.
- PID, TCP listener, HTTP 401 and dry-run are insufficient operational proof.
- Never include secrets in logs, tasks, tests or failures.
- Every production change begins with a focused failing test.

---

### Task 1: Gate local-full on declared readiness

**Files:**
- Modify: `scripts/setup/bootstrap-prerequisites.ps1`
- Modify: `install.ps1`
- Test: `tests/install/test_windows_bootstrap.ps1`

**Interfaces:**
- Produces `Test-HiveMindFullStackReadiness -Root <path> -Profile <profile>`.
- Returns `@{ Ready = bool; Missing = string[]; Diagnostics = object[] }`.

- [ ] **Step 1: Write the failing contract test**

```powershell
$result = Test-HiveMindFullStackReadiness -Root $TestDrive -Profile local-full -Probe { param($name) $false }
Assert-False $result.Ready 'local-full must reject unavailable Docker-backed services'
Assert-Contains $result.Missing 'docker-desktop'
```

- [ ] **Step 2: Verify RED**

Run: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File tests/install/test_windows_bootstrap.ps1`

Expected: fails because the readiness helper does not exist.

- [ ] **Step 3: Implement the minimal helper**

```powershell
function Test-HiveMindFullStackReadiness {
  param([string]$Root, [ValidateSet('local-min','local-full')][string]$Profile, [scriptblock]$Probe)
  if ($Profile -eq 'local-min') { return @{ Ready=$true; Missing=@(); Diagnostics=@() } }
  $required = @('docker-desktop','milvus','ragflow','falkordb','syncthing-watcher')
  $missing = @($required | Where-Object { -not (& $Probe $_) })
  @{ Ready=($missing.Count -eq 0); Missing=$missing; Diagnostics=@() }
}
```

- [ ] **Step 4: Verify GREEN**

Run: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File tests/install/test_windows_bootstrap.ps1; powershell.exe -NoProfile -ExecutionPolicy Bypass -File install.ps1 -Profile local-full -DryRun`

Expected: both exit 0.

- [ ] **Step 5: Commit**

```bash
git add install.ps1 scripts/setup/bootstrap-prerequisites.ps1 tests/install/test_windows_bootstrap.ps1
git commit -m "fix(windows): gate full install on required service readiness"
```

### Task 2: Reconcile supervisor state with actual health

**Files:**
- Modify: `npm/lib/supervisor.js`
- Test: `npm/test/supervisor.test.js`

**Interfaces:**
- Produces `reconcileServiceState(service, current, managedPid, probe)`.
- Returns the observed `healthy` or `degraded` state for a managed child.

- [ ] **Step 1: Write the failing Node test**

```javascript
test('reconciles a stale stopped record with a healthy managed child', async () => {
  const state = await reconcileServiceState({ name: 'worker' }, { state: 'stopped' }, 123, async () => true);
  assert.equal(state.state, 'healthy');
});
```

- [ ] **Step 2: Verify RED**

Run: `node --test npm/test/supervisor.test.js`

Expected: fails because the helper is not exported.

- [ ] **Step 3: Implement the minimal reconciliation**

```javascript
async function reconcileServiceState(service, current, managedPid, probe) {
  if (!managedPid) return current;
  const healthy = await probe(service.healthcheck || service.readiness || { type: 'none' });
  return healthy
    ? { ...current, state: 'healthy', pid: managedPid }
    : { ...current, state: 'degraded', pid: managedPid, last_error: 'healthcheck failed' };
}
```

- [ ] **Step 4: Verify GREEN**

Run: `node --test npm/test/supervisor.test.js`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add npm/lib/supervisor.js npm/test/supervisor.test.js
git commit -m "fix(supervisor): reconcile persisted state with real health"
```

### Task 3: Validate Windows post-reboot required services

**Files:**
- Modify: `scripts/health/validate_after_reboot_windows.py`
- Create: `tests/unit/test_validate_after_reboot_windows.py`
- Modify: `tests/unit/test_validate_after_reboot.py`

**Interfaces:**
- Produces `validate_windows_post_reboot(state_path, required_services) -> dict`.
- Returns `status`, `checks`, `failed_services` and per-service evidence.

- [ ] **Step 1: Write the failing Windows test**

```python
def test_windows_validator_fails_for_required_degraded_service(tmp_path):
    payload = validate_windows_post_reboot(tmp_path / "state.json", ["milvus"])
    assert payload["status"] == "fail"
    assert payload["checks"]["services_healthy"] is False
```

- [ ] **Step 2: Verify RED**

Run: `.\\.venv\\Scripts\\python.exe -m pytest tests/unit/test_validate_after_reboot_windows.py -q`

Expected: import failure before the contract exists.

- [ ] **Step 3: Implement deterministic validation**

```python
def validate_windows_post_reboot(state_path: Path, required_services: list[str]) -> dict:
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    failed = [name for name in required_services if state.get(name, {}).get("state") != "healthy"]
    return {"platform": "windows", "checks": {"supervisor_state_present": state_path.exists(), "services_healthy": not failed}, "failed_services": failed, "status": "ok" if not failed else "fail"}
```

- [ ] **Step 4: Verify GREEN**

Run: `.\\.venv\\Scripts\\python.exe -m pytest tests/unit/test_validate_after_reboot_windows.py tests/unit/test_validate_after_reboot.py -q`

Expected: no Windows skip hides the Windows contract.

- [ ] **Step 5: Commit**

```bash
git add scripts/health/validate_after_reboot_windows.py tests/unit/test_validate_after_reboot_windows.py tests/unit/test_validate_after_reboot.py
git commit -m "fix(windows): validate post-reboot required services"
```

### Task 4: Version M5/M7 runtime artifacts and CI paths

**Files:**
- Create: `scripts/maintenance/backup.py`
- Create: `scripts/release/__init__.py`
- Create: `scripts/release/validate_package.py`
- Create: `.github/workflows/test-windows.yml`
- Create: `tests/unit/test_backup_wrapper.py`
- Create: `tests/unit/test_version_consistency.py`

**Interfaces:**
- `python scripts/maintenance/backup.py --json` runs audit-only by default.
- `python scripts/release/validate_package.py --root <path>` rejects forbidden package artifacts.

- [ ] **Step 1: Write the failing module-path test**

```python
def test_release_validator_module_path_is_importable():
    from scripts.release import validate_package
    assert callable(validate_package.main)
```

- [ ] **Step 2: Verify RED**

Run: `.\\.venv\\Scripts\\python.exe -m pytest tests/unit/test_backup_wrapper.py tests/unit/test_version_consistency.py -q`

Expected: fails because the modules are absent in this clean branch.

- [ ] **Step 3: Add the minimal wrappers and canonical CI reference**

```yaml
- name: Package validation
  run: python scripts/release/validate_package.py --root .
```

- [ ] **Step 4: Verify GREEN**

Run: `.\\.venv\\Scripts\\python.exe -m pytest tests/unit/test_backup_wrapper.py tests/unit/test_version_consistency.py -q`

Expected: targeted tests pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/maintenance scripts/release .github/workflows/test-windows.yml tests/unit/test_backup_wrapper.py tests/unit/test_version_consistency.py
git commit -m "test(windows): validate package and scheduled backup contracts"
```

### Task 5: Add isolated clean-install acceptance and documentation

**Files:**
- Create: `tests/install/run-clean-install-test.ps1`
- Modify: `tests/install/test_windows_bootstrap.ps1`
- Modify: `README.md`
- Modify: `docs/installation.md`
- Create: `docs/windows-services.md`
- Create: `docs/windows-troubleshooting.md`

**Interfaces:**
- `run-clean-install-test.ps1 -Root <path>` returns `Isolated`, `Profile` and `ReportPath`.

- [ ] **Step 1: Write the failing isolation test**

```powershell
$result = & .\\tests\\install\\run-clean-install-test.ps1 -Root $TestDrive
Assert-True $result.Isolated 'clean install must use isolated HOME and LOCALAPPDATA'
```

- [ ] **Step 2: Verify RED**

Run: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File tests/install/test_windows_bootstrap.ps1`

Expected: fails because the clean-install runner is absent.

- [ ] **Step 3: Implement isolated environment creation**

```powershell
$env:HOME = Join-Path $Root 'home'
$env:LOCALAPPDATA = Join-Path $Root 'localappdata'
$env:TEMP = Join-Path $Root 'temp'
$env:TMP = $env:TEMP
```

- [ ] **Step 4: Verify GREEN and documentation contract**

Run: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File tests/install/test_windows_bootstrap.ps1; powershell.exe -NoProfile -ExecutionPolicy Bypass -File tests/install/run-clean-install-test.ps1 -Root $env:TEMP\\hm-clean-test`

Expected: both exit 0, report isolation, and documentation names the real readiness gate.

- [ ] **Step 5: Commit**

```bash
git add tests/install README.md docs
git commit -m "test(windows): add isolated clean-install acceptance"
```

## Final acceptance

- Run real isolated `local-min` installation.
- Run real isolated `local-full` installation after its host dependencies are installed; prove container readiness plus real write/read path.
- Run full unit, integration, E2E, real, Node and PowerShell smoke suites.
- Request explicit reboot authorization, then retain the post-reboot artifact only if `status: ok`.

