# Universal Provider Capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver automatic, durable, cross-platform prompt and event capture for every detected Hive-Mind provider, including real Antigravity Desktop and Codex traffic on Windows after logon.

**Architecture:** Provider-specific parsers feed one normalized `ProviderEvent` contract. A cross-platform `watchdog` service and managed hooks write events to a durable SQLite outbox; a single Claude-Mem sink drains that outbox with retries and idempotency. The existing Hive-Mind supervisor owns the capture service, while a Windows logon task starts the project-root service launcher.

**Tech Stack:** Python 3.12, `watchdog`, SQLite, pytest, PowerShell 5.1+, Node supervisor, Claude-Mem worker HTTP API.

## Global Constraints

- The project runtime is `Python >=3.12,<3.13`; `uv` must provision Python 3.12 when it is absent.
- The canonical root on this machine is `G:\Hive-Mind`; generated startup configuration must persist the installer-resolved root on other machines.
- No provider hook may wait for Claude-Mem, Ollama, or model generation.
- The MCP server must never spawn the universal capture daemon.
- Hooks are installed only for providers with a supported hook/configuration surface.
- Closed providers use file, SQLite/WAL, or bounded polling sources; no binary injection.
- Existing uncommitted user changes must be preserved.
- Every behavioral change is developed test-first.

---

### Task 1: Repair and Validate the Project Python Runtime

**Files:**
- Modify: `install.ps1`
- Modify: `scripts/lib/HiveMind.Windows.psm1`
- Create: `tests/unit/test_windows_runtime_contract.py`

**Interfaces:**
- Produces: `Test-HiveMindPythonRuntime -Root <path>` returning a Boolean.
- Produces: `Repair-HiveMindPythonRuntime -Root <path>` provisioning Python 3.12 with `uv` and recreating `.venv` only when invalid.
- Consumes: `pyproject.toml` requirement `>=3.12,<3.13`.

- [ ] **Step 1: Write failing runtime contract tests**

```python
def test_installer_uses_uv_managed_python_312():
    source = (ROOT / "install.ps1").read_text(encoding="utf-8-sig")
    assert 'uv python install 3.12' in source
    assert 'uv venv --python 3.12' in source
    assert '& py -3.12 -m venv' not in source


def test_runtime_validation_executes_venv_python():
    source = (ROOT / "scripts/lib/HiveMind.Windows.psm1").read_text(encoding="utf-8-sig")
    assert 'function Test-HiveMindPythonRuntime' in source
    assert '--version' in source
```

- [ ] **Step 2: Run the tests and verify failure**

Run: `uv run --python 3.12 --frozen --all-groups pytest tests/unit/test_windows_runtime_contract.py -v`

Expected: FAIL because the installer still calls `py -3.12` and validates only file existence.

- [ ] **Step 3: Implement runtime validation and repair**

Add PowerShell helpers equivalent to:

```powershell
function Test-HiveMindPythonRuntime {
    param([string]$Root)
    $python = Join-Path $Root ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $python)) { return $false }
    & $python --version *> $null
    return $LASTEXITCODE -eq 0
}

function Repair-HiveMindPythonRuntime {
    param([string]$Root)
    & uv python install 3.12
    if ($LASTEXITCODE -ne 0) { throw "uv could not provision Python 3.12" }
    & uv venv --python 3.12 --clear (Join-Path $Root ".venv")
    if ($LASTEXITCODE -ne 0) { throw "uv could not create the project virtual environment" }
}
```

Call repair only when `Test-HiveMindPythonRuntime` is false, then run `uv sync --frozen --all-groups` and validate `import pydantic, watchdog` using the project interpreter.

- [ ] **Step 4: Run focused tests**

Run: `uv run --python 3.12 --frozen --all-groups pytest tests/unit/test_windows_runtime_contract.py tests/unit/test_env_loader.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add install.ps1 scripts/lib/HiveMind.Windows.psm1 tests/unit/test_windows_runtime_contract.py
git commit -m "fix: repair invalid Windows Python runtime"
```

---

### Task 2: Add the Normalized Provider Event Contract

**Files:**
- Create: `scripts/capture/capture_events.py`
- Create: `tests/unit/test_capture_events.py`

**Interfaces:**
- Produces: `EventType` string enum.
- Produces: immutable `ProviderEvent` dataclass.
- Produces: `ProviderEvent.create(...)` with deterministic fallback `event_id`.
- Produces: `ProviderEvent.dedupe_key() -> str` and `as_payload() -> dict`.

- [ ] **Step 1: Write failing event contract tests**

```python
def test_event_dedupe_is_stable_and_provider_scoped():
    a = ProviderEvent.create("codex", "s1", "prompt", "hello", event_id="7")
    b = ProviderEvent.create("codex", "s1", "prompt", "hello", event_id="7")
    c = ProviderEvent.create("antigravity", "s1", "prompt", "hello", event_id="7")
    assert a.dedupe_key() == b.dedupe_key()
    assert a.dedupe_key() != c.dedupe_key()


def test_missing_native_id_gets_deterministic_id():
    first = ProviderEvent.create("kimi", "s", "prompt", "hello", source_position="file:12")
    second = ProviderEvent.create("kimi", "s", "prompt", "hello", source_position="file:12")
    assert first.event_id == second.event_id
```

- [ ] **Step 2: Run and verify failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_capture_events.py -v`

Expected: FAIL because `capture_events.py` does not exist.

- [ ] **Step 3: Implement the contract**

Implement a frozen dataclass with exact fields from the approved design. Validate non-empty provider, session, event type and content. Normalize timestamps to UTC ISO-8601. Derive IDs and dedupe hashes with SHA-256 over canonical JSON.

- [ ] **Step 4: Run focused tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_capture_events.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add scripts/capture/capture_events.py tests/unit/test_capture_events.py
git commit -m "feat: add normalized provider event contract"
```

---

### Task 3: Add the Durable Capture Outbox

**Files:**
- Create: `scripts/capture/capture_queue.py`
- Create: `tests/unit/test_capture_queue.py`

**Interfaces:**
- Consumes: `ProviderEvent`.
- Produces: `CaptureQueue(db_path: Path)`.
- Produces: `enqueue(event) -> bool`, `pending(limit) -> list[QueueItem]`, `mark_delivered(id)`, `mark_retry(id, error, retry_at)`, `move_dead_letter(id, error)`, `health() -> dict`.

- [ ] **Step 1: Write failing durability tests**

```python
def test_queue_survives_restart_and_deduplicates(tmp_path):
    event = ProviderEvent.create("antigravity", "s", "prompt", "unique", event_id="1")
    q1 = CaptureQueue(tmp_path / "capture.db")
    assert q1.enqueue(event) is True
    assert q1.enqueue(event) is False
    q1.close()
    q2 = CaptureQueue(tmp_path / "capture.db")
    assert [item.event.content for item in q2.pending(10)] == ["unique"]


def test_retry_does_not_block_other_sessions(tmp_path):
    queue = CaptureQueue(tmp_path / "capture.db")
    first = ProviderEvent.create("codex", "blocked", "prompt", "one", event_id="1")
    second = ProviderEvent.create("codex", "ready", "prompt", "two", event_id="2")
    queue.enqueue(first)
    queue.enqueue(second)
    blocked = queue.pending(1)[0]
    queue.mark_retry(blocked.id, "worker offline", retry_at=time.time() + 60)
    assert [item.event.session_id for item in queue.pending(10)] == ["ready"]
```

- [ ] **Step 2: Run and verify failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_capture_queue.py -v`

Expected: FAIL because the queue does not exist.

- [ ] **Step 3: Implement SQLite schema and transitions**

Use WAL mode, `busy_timeout`, a unique index on `dedupe_key`, explicit transactions and columns for attempts, next retry, last error, created, delivered and dead-letter timestamps. Keep events ordered by `occurred_at, id` within each session.

- [ ] **Step 4: Run queue tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_capture_queue.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add scripts/capture/capture_queue.py tests/unit/test_capture_queue.py
git commit -m "feat: add durable provider capture outbox"
```

---

### Task 4: Normalize Parser Sessions and Fix Antigravity Desktop

**Files:**
- Modify: `scripts/capture/parsers/antigravity.py`
- Modify: `scripts/capture/capture_adapters.py`
- Create: `scripts/capture/session_events.py`
- Create: `tests/unit/test_antigravity_parser.py`
- Create: `tests/unit/test_capture_adapters_windows.py`

**Interfaces:**
- Produces: Antigravity parser sessions with every prompt and stable source positions.
- Produces: `session_to_events(provider, session) -> list[ProviderEvent]`.
- Consumes: both `~/.gemini/antigravity` and `~/.gemini/antigravity-cli` layouts.

- [ ] **Step 1: Write failing parser and adapter tests**

```python
def test_antigravity_keeps_every_user_input(tmp_path):
    transcript = tmp_path / "68f4d64e-9de6-4f73-99f7-66f173d38de0" / ".system_generated" / "logs" / "transcript_full.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_text("\n".join([
        json.dumps({"step_index": 1, "type": "USER_INPUT", "content": "<USER_REQUEST>one</USER_REQUEST>"}),
        json.dumps({"step_index": 2, "type": "USER_INPUT", "content": "<USER_REQUEST>two</USER_REQUEST>"}),
    ]), encoding="utf-8")
    session = parse(transcript)[0]
    assert session["prompts"] == ["one", "two"]
    assert session["prompt_events"][1]["event_id"] == "2"


def test_registry_includes_antigravity_desktop_home(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    module = reload_capture_adapters()
    assert any(".gemini/antigravity/brain" in p.replace("\\", "/") for p in module.ADAPTERS["antigravity"]["sources"])
```

- [ ] **Step 2: Run and verify failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_antigravity_parser.py tests/unit/test_capture_adapters_windows.py -v`

Expected: FAIL because only the last prompt and CLI path are currently retained.

- [ ] **Step 3: Implement parser and Windows paths**

Collect prompts rather than overwriting them. Use `step_index` as native event ID. Add Desktop and CLI source/watch globs. Resolve VS Code storage through `%APPDATA%\Code\User` on Windows and retain POSIX paths elsewhere.

- [ ] **Step 4: Implement session normalization**

Map prompts, tool calls/results and final assistant content to ordered `ProviderEvent` objects. Preserve existing parser dictionaries for compatibility with the tailer during migration.

- [ ] **Step 5: Run focused and existing parser tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_antigravity_parser.py tests/unit/test_capture_adapters_windows.py tests/unit/test_codex_parser.py tests/unit/test_capture_core.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add scripts/capture/parsers/antigravity.py scripts/capture/capture_adapters.py scripts/capture/session_events.py tests/unit/test_antigravity_parser.py tests/unit/test_capture_adapters_windows.py
git commit -m "fix: capture every Antigravity Desktop prompt"
```

---

### Task 5: Replace Linux-Only inotify with Cross-Platform Sources

**Files:**
- Create: `scripts/capture/capture_sources.py`
- Modify: `scripts/capture/capture-realtime.py`
- Modify: `tests/unit/test_capture_realtime.py`
- Create: `tests/unit/test_capture_sources.py`

**Interfaces:**
- Produces: `SourceChange(provider: str, path: Path, detected_at: float)`.
- Produces: `WatchdogSource(registry, callback)`, `PollingReconciler(registry, callback, interval=5.0)`.
- Consumes: provider source/watch globs from the registry.

- [ ] **Step 1: Remove the Windows skip and write failing source tests**

```python
def test_capture_realtime_imports_without_libc():
    module = load_capture_realtime()
    assert not hasattr(module, "_libc")


def test_polling_detects_rewritten_transcript_once(tmp_path):
    transcript = tmp_path / "transcript_full.jsonl"
    transcript.write_text("{}\n", encoding="utf-8")
    changes = []
    source = PollingReconciler(
        {"antigravity": [str(transcript)]},
        lambda change: changes.append(change),
        interval=0,
    )
    source.scan_once()
    transcript.write_text('{"type":"USER_INPUT"}\n', encoding="utf-8")
    source.scan_once()
    source.scan_once()
    assert [(change.provider, change.path) for change in changes] == [
        ("antigravity", transcript)
    ]
```

- [ ] **Step 2: Run and verify failure on Windows**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_capture_realtime.py tests/unit/test_capture_sources.py -v`

Expected: FAIL at `ctypes.CDLL("libc.so.6")`.

- [ ] **Step 3: Implement watchdog plus reconciliation**

Use `watchdog.observers.Observer` for platform-native notifications. Watch the nearest existing non-glob ancestor for each source. Coalesce changes per provider for 400 ms. Run a five-second reconciliation scan keyed by path, mtime nanoseconds and size to recover missed notifications and discover new session directories.

- [ ] **Step 4: Rewrite the daemon entrypoint**

The daemon must initialize the registry, queue, source manager and drain loop. Remove direct `ctypes`, `select`, `inotify_*` constants and nested platform branches. Emit structured logs and a project-local PID file.

- [ ] **Step 5: Run capture source tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_capture_realtime.py tests/unit/test_capture_sources.py tests/unit/test_capture_tailer.py -v`

Expected: PASS on Windows without skips.

- [ ] **Step 6: Commit**

```powershell
git add scripts/capture/capture_sources.py scripts/capture/capture-realtime.py tests/unit/test_capture_realtime.py tests/unit/test_capture_sources.py
git commit -m "feat: add cross-platform realtime capture sources"
```

---

### Task 6: Add the Claude-Mem Sink and Offline Drain

**Files:**
- Create: `scripts/capture/capture_sink.py`
- Modify: `scripts/capture/capture-realtime.py`
- Create: `tests/unit/test_capture_sink.py`
- Create: `tests/integration/test_capture_offline_recovery.py`

**Interfaces:**
- Produces: `ClaudeMemSink(base_url, timeout)` with `deliver(event) -> DeliveryResult`.
- Produces: `OutboxDrainer(queue, sink, max_attempts=8)` with `drain_once(limit=100) -> dict`.
- Consumes: Claude-Mem session endpoints and durable `CaptureQueue`.

- [ ] **Step 1: Write failing endpoint mapping tests**

```python
@pytest.mark.parametrize((event_type, endpoint), [
    ("session_start", "/api/sessions/init"),
    ("prompt", "/api/sessions/init"),
    ("tool_use", "/api/sessions/observations"),
    ("tool_result", "/api/sessions/observations"),
    ("assistant", "/api/sessions/summarize"),
    ("session_end", "/api/sessions/summarize"),
])
def test_sink_maps_event_to_worker_endpoint(event_type, endpoint, monkeypatch):
    requested = []

    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return False
        def read(self):
            return b'{"stored":true}'

    def fake_urlopen(req, timeout):
        requested.append(req.full_url)
        return Response()

    monkeypatch.setattr(capture_sink.request, "urlopen", fake_urlopen)
    event = ProviderEvent.create("codex", "s", event_type, "payload", event_id="1")
    result = ClaudeMemSink("http://127.0.0.1:37700").deliver(event)
    assert result.endpoint == endpoint
    assert requested == ["http://127.0.0.1:37700" + endpoint]
```

- [ ] **Step 2: Write failing offline recovery test**

Queue an event while a fake worker returns connection failure, restart the drainer against a healthy fake worker, and assert the event becomes delivered exactly once.

- [ ] **Step 3: Run and verify failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_capture_sink.py tests/integration/test_capture_offline_recovery.py -v`

Expected: FAIL because sink and drainer do not exist.

- [ ] **Step 4: Implement sink, retries and dead letters**

Use short HTTP timeouts, classify 4xx as permanent except 408/429, classify network and 5xx as retryable, apply exponential backoff capped at 60 seconds, and move an item to dead letter after eight attempts. Preserve order within each session while allowing unrelated sessions to progress.

- [ ] **Step 5: Run focused tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_capture_sink.py tests/integration/test_capture_offline_recovery.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add scripts/capture/capture_sink.py scripts/capture/capture-realtime.py tests/unit/test_capture_sink.py tests/integration/test_capture_offline_recovery.py
git commit -m "feat: deliver captured provider events reliably"
```

---

### Task 7: Add Managed Hooks Without Blocking Providers

**Files:**
- Create: `scripts/capture/capture-hook.py`
- Create: `scripts/setup/install-capture-hooks.py`
- Modify: `scripts/setup/register-mcp.ps1`
- Modify: `scripts/setup/register-mcp.sh`
- Create: `tests/unit/test_capture_hook.py`
- Create: `tests/unit/test_install_capture_hooks.py`

**Interfaces:**
- Produces: CLI `capture-hook.py --provider NAME --event-type TYPE` reading JSON from stdin and writing only to `CaptureQueue`.
- Produces: idempotent `install-capture-hooks.py --check|--install` preserving unrelated provider settings.
- Produces: `merge_hooks(settings: dict, provider: str, command: str) -> dict` for deterministic configuration updates.

- [ ] **Step 1: Write failing non-blocking hook tests**

```python
def test_hook_succeeds_when_worker_is_offline(tmp_path, monkeypatch):
    monkeypatch.setenv("HIVE_CAPTURE_DB", str(tmp_path / "capture.db"))
    result = run_hook("codex", "prompt", {"session_id": "s", "prompt": "hello"})
    assert result.returncode == 0
    assert CaptureQueue(tmp_path / "capture.db").health()["pending"] == 1


def test_installer_preserves_unrelated_hooks(tmp_path):
    settings = {
        "hooks": {
            "UserPromptSubmit": [
                {"hooks": [{"type": "command", "command": "foreign-hook"}]}
            ]
        }
    }
    merged = merge_hooks(settings, "codex", "python capture-hook.py --provider codex --event-type prompt")
    commands = [
        hook["command"]
        for group in merged["hooks"]["UserPromptSubmit"]
        for hook in group["hooks"]
    ]
    assert "foreign-hook" in commands
    assert commands.count("python capture-hook.py --provider codex --event-type prompt") == 1
```

- [ ] **Step 2: Run and verify failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_capture_hook.py tests/unit/test_install_capture_hooks.py -v`

Expected: FAIL because the hook entrypoint and installer do not exist.

- [ ] **Step 3: Implement hook input adapters**

Support Claude/Codex-style fields and generic `session_id`, `cwd`, `prompt`, `tool_name`, `tool_input`, `tool_response`, and `last_assistant_message`. Reject oversized stdin before JSON parsing, redact secrets, enqueue, print one compact JSON result and exit zero.

- [ ] **Step 4: Implement idempotent provider configuration**

Detect supported hook surfaces and merge only Hive-Mind-owned records. Never replace whole settings files. Add `--check` output showing installed, missing and unsupported providers.

- [ ] **Step 5: Run hook tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_capture_hook.py tests/unit/test_install_capture_hooks.py tests/integration/test_agent_hooks_materialized.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add scripts/capture/capture-hook.py scripts/setup/install-capture-hooks.py scripts/setup/register-mcp.ps1 scripts/setup/register-mcp.sh tests/unit/test_capture_hook.py tests/unit/test_install_capture_hooks.py
git commit -m "feat: install non-blocking provider capture hooks"
```

---

### Task 8: Enable the Capture Service and Register Windows Logon Startup

**Files:**
- Modify: `scripts/setup/install_services.py`
- Modify: `npm/lib/supervisor.js`
- Create: `scripts/services/start-hive-mind.ps1`
- Create: `scripts/setup/register-windows-startup.ps1`
- Modify: `install.ps1`
- Modify: `tests/unit/test_service_backends.py`
- Create: `tests/unit/test_windows_startup_contract.py`

**Interfaces:**
- Produces: runnable `sinapse-capture-realtime` service on Windows.
- Produces: `register-windows-startup.ps1 -Root <path> -Check`.
- Produces: scheduled task `Hive-Mind Services` triggered at current-user logon.

- [ ] **Step 1: Write failing service/startup tests**

```python
def test_capture_service_is_not_optional_on_windows():
    spec = next(s for s in install_services.service_specs() if s["name"] == "sinapse-capture-realtime")
    assert spec.get("optional", False) is False


def test_windows_startup_targets_project_launcher():
    source = (ROOT / "scripts/setup/register-windows-startup.ps1").read_text(encoding="utf-8-sig")
    assert "Hive-Mind Services" in source
    assert "start-hive-mind.ps1" in source
    assert ".gemini" not in source
```

- [ ] **Step 2: Run and verify failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_service_backends.py tests/unit/test_windows_startup_contract.py -v`

Expected: FAIL because Windows marks capture optional and has no startup registrar.

- [ ] **Step 3: Enable supervisor ownership**

Remove the Windows-only optional flag. Ensure `runnableServices()` includes the service. Keep the MCP free of capture auto-start logic. Add capture status to `services status`.

- [ ] **Step 4: Implement the logon launcher**

`start-hive-mind.ps1` resolves the project-local Node CLI, starts services idempotently and logs to `logs/startup.log`. `register-windows-startup.ps1` creates or updates a current-user scheduled task with hidden PowerShell, the resolved root and no temporary paths. `-Check` compares action and trigger without mutation.

- [ ] **Step 5: Wire registration into install.ps1**

After service manifest validation, register startup and start services. Installation fails with a clear message if registration or immediate startup fails.

- [ ] **Step 6: Run focused tests and manifest check**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_service_backends.py tests/unit/test_windows_startup_contract.py tests/unit/test_install_services.py -v`

Run: `node .\npm\bin\hive-mind.js services status`

Expected: tests PASS and status lists `sinapse-capture-realtime`.

- [ ] **Step 7: Commit**

```powershell
git add scripts/setup/install_services.py npm/lib/supervisor.js scripts/services/start-hive-mind.ps1 scripts/setup/register-windows-startup.ps1 install.ps1 tests/unit/test_service_backends.py tests/unit/test_windows_startup_contract.py
git commit -m "feat: start universal capture automatically on Windows"
```

---

### Task 9: Expose Provider Health and Synthetic Verification

**Files:**
- Create: `scripts/capture/capture_health.py`
- Modify: `core/memory/health.py`
- Modify: `scripts/services/sinapse_mcp.py`
- Create: `scripts/health/verify-provider-capture.py`
- Create: `tests/unit/test_capture_health.py`
- Create: `tests/integration/test_provider_capture_synthetic.py`

**Interfaces:**
- Produces: `capture_health(provider_states: dict, queue_health: dict) -> {service, queue, providers}`.
- Produces: CLI `verify-provider-capture.py --provider NAME --timeout 15`.
- Extends: `sinapse_health` with provider source, state, last detected, last delivered, pending, error and restart count.

- [ ] **Step 1: Write failing health shape tests**

```python
def test_capture_health_reports_each_detected_provider(tmp_path):
    states = {
        "codex": {"state": "watching", "transport": "managed_hook"},
        "antigravity": {"state": "watching", "transport": "filesystem"},
    }
    result = capture_health(states, {"pending": 0, "dead_letter": 0})
    assert set(result["providers"]) == {"codex", "antigravity"}
    assert {"state", "transport", "last_detected", "last_delivered", "pending", "last_error"} <= set(result["providers"]["codex"])
```

- [ ] **Step 2: Run and verify failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_capture_health.py tests/integration/test_provider_capture_synthetic.py -v`

Expected: FAIL because provider health is absent.

- [ ] **Step 3: Implement health snapshots**

Persist per-provider runtime state in the capture database. Health reads must be quick and must not wake inactive providers.

- [ ] **Step 4: Implement synthetic verification**

Inject a uniquely tagged event through the selected provider source adapter, wait for outbox delivery, then query Claude-Mem temporal search for the tag. Return nonzero on detection, queue, delivery, lookup or duplication failure.

- [ ] **Step 5: Run focused tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_capture_health.py tests/integration/test_provider_capture_synthetic.py tests/unit/test_sinapse_mcp.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add scripts/capture/capture_health.py core/memory/health.py scripts/services/sinapse_mcp.py scripts/health/verify-provider-capture.py tests/unit/test_capture_health.py tests/integration/test_provider_capture_synthetic.py
git commit -m "feat: report and verify provider capture health"
```

---

### Task 10: Prove Clean Installation and Real Prompt Capture

**Files:**
- Modify: `tests/install/run-clean-install-test.ps1`
- Modify: `tests/run_all.ps1`
- Create: `tests/e2e/test_windows_provider_capture.py`
- Modify: `docs/installation.md`

**Interfaces:**
- Consumes: installer, Windows startup task, provider health CLI and live Claude-Mem.
- Produces: reproducible evidence for clean install, offline recovery, Antigravity capture, Codex capture and restart idempotency.
- Test fixture `LiveCaptureStack` produces `stop_claude_mem()`, `start_claude_mem()` and `wait_for_temporal_tags(tags, timeout)`.
- Test fixture `TranscriptFixture` produces `append_prompts(count) -> list[str]` and `append_prompt() -> str` for isolated Antigravity/Codex sources.

- [ ] **Step 1: Add failing E2E assertions**

```python
def test_live_antigravity_transcript_captures_every_prompt(live_stack, antigravity_fixture):
    tags = antigravity_fixture.append_prompts(3)
    assert live_stack.wait_for_temporal_tags(tags, timeout=20) == set(tags)


def test_capture_survives_worker_restart_without_duplicates(live_stack, codex_fixture):
    live_stack.stop_claude_mem()
    tag = codex_fixture.append_prompt()
    live_stack.start_claude_mem()
    assert live_stack.temporal_count(tag, timeout=30) == 1
```

- [ ] **Step 2: Run E2E tests and confirm they fail before final wiring**

Run: `.\.venv\Scripts\python.exe -m pytest tests/e2e/test_windows_provider_capture.py -v`

Expected: FAIL until runtime registration and live capture are fully wired.

- [ ] **Step 3: Extend clean-install validation**

Assert compatible Python provisioning, project-local `.venv`, scheduled task action, active supervisor, active capture service, healthy Claude-Mem sink and detected provider states. Keep secrets out of test output.

- [ ] **Step 4: Run the installer and focused E2E suite**

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -Profile local-full`

Run: `.\.venv\Scripts\python.exe -m pytest tests/e2e/test_windows_provider_capture.py -v`

Expected: installer exits 0 and E2E tests PASS.

- [ ] **Step 5: Validate current Codex and Antigravity traffic**

Run provider verification for `codex` and `antigravity`, then use Sinapse temporal search to confirm unique tags and current-session prompts are present exactly once.

Expected: both providers report `healthy`; every injected/current tag is searchable once.

- [ ] **Step 6: Validate restart and logon registration**

Restart the supervisor, confirm the queue drains without duplication, and run `register-windows-startup.ps1 -Check`. A real logoff/logon remains the final machine-level acceptance action if the environment cannot trigger it safely during automation.

- [ ] **Step 7: Run the complete relevant suite**

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File .\tests\run_all.ps1`

Expected: no capture/runtime regression; service-offline skips are not accepted for Claude-Mem, Codex or Antigravity in this validation.

- [ ] **Step 8: Update documentation and commit**

```powershell
git add tests/install/run-clean-install-test.ps1 tests/run_all.ps1 tests/e2e/test_windows_provider_capture.py docs/installation.md
git commit -m "test: verify Windows provider capture end to end"
```
