#!/usr/bin/env python3
"""
capture-realtime.py — Cross-platform realtime capture daemon.

Orquestrador fino sobre fontes multiplataforma (watchdog + reconciliador de
polling). Dono das fontes owner=="realtime". A QUALQUER mudança numa fonte de
um provider, re-parseia com o parser DEDICADO (capture_adapters) e entrega ao
Claude-Mem pelo mesmo motor ``capture_core.ingest`` usado pelo runtime Linux
funcional. A idempotência por content-hash no SeenStore impede duplicação mesmo
com reparse, reinício ou dois processos concorrentes.

A outbox experimental não participa do caminho principal de captura. Hooks
legados podem continuar escrevendo nela, mas parser → Claude-Mem não depende
mais de um drainer ausente. O MCP server nunca deve iniciar este daemon.
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
from hive_mind.projects.identity import ProjectIdentityResolver  # noqa: E402
from hive_mind.capture import ingest as capture  # noqa: E402
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
    print(json.dumps(record, ensure_ascii=True, default=str), file=stream, flush=True)


# ── motor do daemon ────────────────────────────────────────────────────────────
class RealtimeCapture:
    """Parse changed provider sources and deliver with Linux-compatible ingest."""

    def __init__(
        self,
        registry: dict,
        store: "core.SeenStore",
        *,
        window_s: float = WINDOW_S,
        live_max_age_s: float = LIVE_MAX_AGE_S,
        clock=time.time,
        resolver: ProjectIdentityResolver | None = None,
    ) -> None:
        self._registry = registry
        self._store = store
        self._window_s = float(window_s)
        self._live_max_age_s = float(live_max_age_s)
        self._clock = clock
        self._resolver = resolver or ProjectIdentityResolver()
        self._lock = threading.Lock()

    def handle_change(self, change: SourceChange) -> int:
        """Re-parse changed sources and deliver new content to Claude-Mem."""
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
                delivered = self._ingest_paths(provider, adapter, targets)
                if delivered:
                    log_event("info", "catch_up_provider", provider=provider, delivered=delivered)
                total += delivered
        return total

    def _ingest_paths(self, provider: str, adapter: dict, targets: list[Path]) -> int:
        parser = adapter["parser"]
        delivered = 0
        for path in targets:
            try:
                for session in parser(path) or []:
                    # No attach_project_identity here any more: ingest()
                    # resolves identity for every entrypoint, so there is
                    # nothing left for this one to forget (D004-R2).
                    delivered += capture.ingest(
                        provider,
                        session,
                        self._store,
                        resolver=self._resolver,
                        default_surface=adapter.get("surface") or "unknown",
                        on_degraded=lambda identity: log_event(
                            "warning", "project_identity_unclassified",
                            provider=provider, project_id=identity.project_id,
                        ),
                        on_refused=lambda refused: log_event(
                            "warning", "project_identity_refused",
                            provider=provider, reason=refused.reason,
                            detail=refused.detail,
                        ),
                    )
            except Exception as exc:
                log_event("warning", "parse_or_delivery_failed", provider=provider, path=str(path), error=str(exc))
        if delivered:
            log_event("info", "sessions_delivered", provider=provider, count=delivered)
        return delivered

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


# ── ciclo de vida ──────────────────────────────────────────────────────────────
def _write_pid_file() -> None:
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")


def _remove_pid_file() -> None:
    try:
        PID_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def main() -> int:
    registry = ADAPTERS
    store = core.SeenStore()
    daemon = RealtimeCapture(registry, store)
    _write_pid_file()
    log_event(
        "info", "daemon_started",
        pid=os.getpid(),
        transport="capture_core.ingest",
        providers=sorted(registry),
        pid_file=str(PID_FILE),
    )

    delivered = daemon.catch_up()
    log_event("info", "catch_up_complete", delivered=delivered)

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
    except KeyboardInterrupt:
        log_event("info", "daemon_stopping", reason="keyboard_interrupt")
    finally:
        reconciler.stop()
        watcher.stop()
        store.close()
        _remove_pid_file()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
