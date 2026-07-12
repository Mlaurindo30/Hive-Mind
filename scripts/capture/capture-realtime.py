#!/usr/bin/env python3
"""
capture-realtime.py — Cross-platform realtime capture daemon.

Orquestrador fino sobre fontes multiplataforma (watchdog + reconciliador de
polling). Dono das fontes owner=="realtime". A QUALQUER mudança numa fonte de
um provider, re-parseia com o parser DEDICADO (capture_adapters), normaliza as
sessões em ProviderEvent e ENFILEIRA no outbox durável (CaptureQueue). O
dedupe_key do evento garante idempotência: re-parse N vezes → cada evento
persiste 1x só.

Entrega ao Claude-Mem é responsabilidade do drainer do outbox (Task 6 — ver o
seam ``_drain_outbox``). Este daemon NUNCA espera pelo Claude-Mem/Ollama e não
faz chamadas de rede. O MCP server nunca deve iniciá-lo.
"""
from __future__ import annotations

import fnmatch
import glob as globmod
import json
import os
import sys
import threading
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[2]
for _entry in (str(_HERE), str(ROOT)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

import capture_core as core                                # noqa: E402
from capture_adapters import adapters_by_owner             # noqa: E402
from scripts.capture.capture_events import ProviderEvent   # noqa: E402
from scripts.capture.capture_queue import CaptureQueue     # noqa: E402
from scripts.capture.capture_sources import (              # noqa: E402
    PollingReconciler,
    SourceChange,
    WatchdogSource,
)

ADAPTERS = adapters_by_owner("realtime")

WINDOW_S = 2 * 3600          # só sessões ativas nesta janela no catch-up
LIVE_MAX_AGE_S = 120.0       # em evento ao vivo, só re-parseia fontes recém-tocadas
RECONCILE_INTERVAL_S = 5.0   # varredura de reconciliação (recupera eventos perdidos)
PID_FILE = ROOT / "logs" / "capture-realtime.pid"


def log_event(level: str, event: str, **fields) -> None:
    """Structured single-line JSON log record."""
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "level": level,
        "event": event,
        **fields,
    }
    stream = sys.stderr if level in ("error", "warning") else sys.stdout
    print(json.dumps(record, ensure_ascii=False, default=str), file=stream, flush=True)


# ── normalização sessão → ProviderEvent ────────────────────────────────────────
def session_to_provider_events(provider: str, session: dict) -> list[ProviderEvent]:
    """Normalize one parser session dict into ordered ProviderEvents.

    Prefers ``scripts.capture.session_events.session_to_events`` (Task 4)
    when available; otherwise applies a compatible local mapping over the
    legacy parser dict shape {sid, prompt, prompts, turns, last, ...}.
    """
    try:
        from scripts.capture.session_events import session_to_events  # type: ignore
    except ImportError:
        return _fallback_session_events(provider, session)
    return list(session_to_events(provider, session))


def _fallback_session_events(provider: str, session: dict) -> list[ProviderEvent]:
    sid = str(session.get("sid") or "").strip()
    if not sid:
        return []
    events: list[ProviderEvent] = []

    prompts = [str(p) for p in (session.get("prompts") or []) if str(p).strip()]
    if not prompts and str(session.get("prompt") or "").strip():
        prompts = [str(session["prompt"])]
    prompt_meta = session.get("prompt_events") or []
    for index, text in enumerate(prompts):
        meta = prompt_meta[index] if index < len(prompt_meta) and isinstance(prompt_meta[index], dict) else {}
        event_id = str(meta["event_id"]) if meta.get("event_id") else None
        events.append(
            ProviderEvent.create(
                provider, sid, "prompt", text,
                event_id=event_id,
                source_position=f"prompt:{index}",
            )
        )

    for index, turn in enumerate(session.get("turns") or []):
        if not isinstance(turn, dict):
            continue
        tool_name = str(turn.get("tool_name") or "Tool").strip() or "Tool"
        tool_input = turn.get("tool_input")
        if isinstance(tool_input, dict):
            embedded = str(tool_input.get("prompt") or "").strip()
            if embedded:
                events.append(
                    ProviderEvent.create(
                        provider, sid, "prompt", embedded,
                        source_position=f"turn:{index}:prompt",
                    )
                )
        response = str(turn.get("tool_response") or "").strip()
        if response:
            events.append(
                ProviderEvent.create(
                    provider, sid, "tool_result", f"[{tool_name}] {response}",
                    source_position=f"turn:{index}:{tool_name}",
                )
            )

    last = str(session.get("last") or "").strip()
    if last:
        events.append(
            ProviderEvent.create(
                provider, sid, "assistant", last,
                source_position="last",
            )
        )
    return events


# ── motor do daemon ────────────────────────────────────────────────────────────
class RealtimeCapture:
    """Parse changed provider sources and enqueue normalized events durably."""

    def __init__(
        self,
        registry: dict,
        queue: CaptureQueue,
        *,
        window_s: float = WINDOW_S,
        live_max_age_s: float = LIVE_MAX_AGE_S,
        clock=time.time,
    ) -> None:
        self._registry = registry
        self._queue = queue
        self._window_s = float(window_s)
        self._live_max_age_s = float(live_max_age_s)
        self._clock = clock
        self._lock = threading.Lock()

    def handle_change(self, change: SourceChange) -> int:
        """Re-parse the changed provider source(s) and enqueue new events."""
        adapter = self._registry.get(change.provider)
        if not adapter:
            return 0
        with self._lock:
            now = self._clock()
            core.SESSION_CUTOFF_MS = int((now - self._window_s) * 1000)
            if change.path.is_file() and self._matches_source(change.provider, change.path):
                targets = [change.path]
            else:
                cutoff = now - self._live_max_age_s
                targets = [
                    p for p in self._expand_sources(change.provider)
                    if core._src_mtime(p) >= cutoff
                ]
            return self._ingest_paths(change.provider, adapter, targets)

    def catch_up(self) -> int:
        """Startup pass: parse every provider source active inside the window."""
        total = 0
        with self._lock:
            now = self._clock()
            core.SESSION_CUTOFF_MS = int((now - self._window_s) * 1000)
            cutoff = now - self._window_s
            for provider, adapter in self._registry.items():
                targets = [
                    p for p in self._expand_sources(provider)
                    if core._src_mtime(p) >= cutoff
                ]
                enqueued = self._ingest_paths(provider, adapter, targets)
                if enqueued:
                    log_event("info", "catch_up_provider", provider=provider, enqueued=enqueued)
                total += enqueued
        return total

    def _ingest_paths(self, provider: str, adapter: dict, targets: list[Path]) -> int:
        parser = adapter["parser"]
        enqueued = 0
        for path in targets:
            try:
                for session in parser(path) or []:
                    for event in session_to_provider_events(provider, session):
                        if self._queue.enqueue(event):
                            enqueued += 1
            except Exception as exc:
                log_event("warning", "parse_failed", provider=provider, path=str(path), error=str(exc))
        if enqueued:
            log_event("info", "events_enqueued", provider=provider, count=enqueued)
        return enqueued

    def _expand_sources(self, provider: str) -> list[Path]:
        paths: list[Path] = []
        for pattern in self._registry[provider].get("sources") or []:
            for match in globmod.glob(str(pattern), recursive=True):
                candidate = Path(match)
                if candidate.is_file():
                    paths.append(candidate)
        return paths

    def _matches_source(self, provider: str, path: Path) -> bool:
        normalized = str(path).replace("\\", "/").lower()
        for pattern in self._registry[provider].get("sources") or []:
            glob_pattern = str(pattern).replace("\\", "/").lower()
            if fnmatch.fnmatchcase(normalized, glob_pattern):
                return True
        return False


# ── seam de entrega (Task 6) ───────────────────────────────────────────────────
def _drain_outbox(queue: CaptureQueue) -> None:
    """Delivery seam — intentionally a no-op in this daemon.

    Task 6 plugs ``OutboxDrainer(queue, ClaudeMemSink())`` here. Until then
    events stay durably persisted in the CaptureQueue outbox; the daemon never
    talks to (or waits for) Claude-Mem.
    """
    return None


# ── ciclo de vida ──────────────────────────────────────────────────────────────
def _write_pid_file() -> None:
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")


def _remove_pid_file() -> None:
    try:
        PID_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def _queue_path() -> Path:
    override = os.environ.get("HIVE_CAPTURE_DB")
    if override:
        return Path(override)
    return core.DATA_DIR / "capture.db"


def main() -> int:
    registry = ADAPTERS
    queue = CaptureQueue(_queue_path())
    daemon = RealtimeCapture(registry, queue)
    _write_pid_file()
    log_event(
        "info", "daemon_started",
        pid=os.getpid(),
        queue=str(_queue_path()),
        providers=sorted(registry),
        pid_file=str(PID_FILE),
    )

    enqueued = daemon.catch_up()
    log_event("info", "catch_up_complete", enqueued=enqueued)

    watch_registry = {
        provider: list(adapter.get("watch") or []) + list(adapter.get("sources") or [])
        for provider, adapter in registry.items()
    }
    source_registry = {
        provider: list(adapter.get("sources") or [])
        for provider, adapter in registry.items()
    }
    watcher = WatchdogSource(watch_registry, daemon.handle_change)
    reconciler = PollingReconciler(source_registry, daemon.handle_change, interval=RECONCILE_INTERVAL_S)
    # Prime the reconciler baseline right after catch-up so its first real
    # cycle only reports genuinely new changes.
    reconciler.scan_once()
    watcher.start()
    reconciler.start()
    log_event(
        "info", "sources_started",
        watch_roots=[str(root) for root in watcher.watch_roots()],
        reconcile_interval_s=RECONCILE_INTERVAL_S,
    )

    try:
        while True:
            time.sleep(30)
            _drain_outbox(queue)
            log_event("debug", "queue_health", **queue.health())
    except KeyboardInterrupt:
        log_event("info", "daemon_stopping", reason="keyboard_interrupt")
    finally:
        reconciler.stop()
        watcher.stop()
        queue.close()
        _remove_pid_file()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
