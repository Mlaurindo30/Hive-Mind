"""Cross-platform change sources for the realtime capture daemon.

Two complementary detectors feed the daemon with ``SourceChange`` callbacks:

* ``WatchdogSource`` — platform-native filesystem notifications through
  ``watchdog.observers.Observer``. Each provider glob is reduced to its
  nearest existing non-glob ancestor directory, which is watched
  recursively. Bursts are coalesced per provider for a short window so a
  heavy rewrite emits a single change.
* ``PollingReconciler`` — a bounded periodic scan keyed by
  ``(path, mtime_ns, size)`` that recovers notifications the observer may
  have missed and discovers new session files. A rewrite is detected
  exactly once; the first scan only primes the baseline.

Neither detector performs network I/O; both consume a read-only registry
mapping ``provider -> [glob patterns]``.
"""
from __future__ import annotations

import glob as _glob
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

_GLOB_CHARS = ("*", "?", "[")

Registry = Mapping[str, Sequence[str]]


@dataclass(frozen=True)
class SourceChange:
    """A detected change in one provider's capture source."""

    provider: str
    path: Path
    detected_at: float


def nearest_existing_ancestor(pattern: str) -> Path | None:
    """Return the closest existing directory above the glob part of *pattern*.

    ``C:/x/sessions/*/rollout-*.jsonl`` resolves to ``C:/x/sessions`` when it
    exists, otherwise walks up until an existing directory is found. Returns
    ``None`` when no non-glob ancestor exists at all.
    """
    parts = Path(pattern).parts
    literal_parts: list[str] = []
    for part in parts:
        if any(char in part for char in _GLOB_CHARS):
            break
        literal_parts.append(part)
    if not literal_parts:
        return None
    candidate = Path(*literal_parts)
    if len(literal_parts) == len(parts) and candidate.is_file():
        # Pattern had no glob at all: watch the parent directory of the file.
        candidate = candidate.parent
    while True:
        if candidate.is_dir():
            return candidate
        parent = candidate.parent
        if parent == candidate:
            return None
        candidate = parent


class _RootHandler(FileSystemEventHandler):
    """Forward filesystem events under one watched root to the source."""

    def __init__(self, source: "WatchdogSource", providers: tuple[str, ...]) -> None:
        self._source = source
        self._providers = providers

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        raw = getattr(event, "dest_path", "") or event.src_path
        if isinstance(raw, bytes):
            raw = raw.decode(errors="replace")
        self._source.record(self._providers, Path(raw))


class WatchdogSource:
    """Native filesystem notifications, coalesced per provider.

    The first event for an idle provider starts a coalescing window of
    ``coalesce_seconds``; further events inside the window only refresh the
    reported path. When the window elapses a single ``SourceChange`` is
    delivered to the callback.
    """

    def __init__(
        self,
        registry: Registry,
        callback: Callable[[SourceChange], None],
        *,
        coalesce_seconds: float = 0.4,
    ) -> None:
        self._registry = {provider: list(patterns) for provider, patterns in registry.items()}
        self._callback = callback
        self._coalesce_seconds = max(0.0, float(coalesce_seconds))
        self._lock = threading.Lock()
        self._pending: dict[str, Path] = {}
        self._timers: dict[str, threading.Timer] = {}
        self._observer: Observer | None = None
        self._stopped = False

    def watch_roots(self) -> dict[Path, tuple[str, ...]]:
        """Map each nearest existing non-glob ancestor to its providers."""
        roots: dict[Path, set[str]] = {}
        for provider, patterns in self._registry.items():
            for pattern in patterns:
                root = nearest_existing_ancestor(str(pattern))
                if root is not None:
                    roots.setdefault(root, set()).add(provider)
        # Drop roots nested under another watched root with the same providers:
        # recursive watches on the ancestor already cover them.
        result: dict[Path, tuple[str, ...]] = {}
        for root, providers in roots.items():
            covered = any(
                other != root and other in root.parents and providers <= roots[other]
                for other in roots
            )
            if not covered:
                result[root] = tuple(sorted(providers))
        return result

    def start(self) -> None:
        """Schedule recursive watches on every resolved root and start observing."""
        if self._observer is not None:
            return
        self._stopped = False
        observer = Observer()
        for root, providers in self.watch_roots().items():
            observer.schedule(_RootHandler(self, providers), str(root), recursive=True)
        observer.daemon = True
        observer.start()
        self._observer = observer

    def record(self, providers: Iterable[str], path: Path) -> None:
        """Register a raw event for *providers*, coalescing per provider."""
        with self._lock:
            if self._stopped:
                return
            for provider in providers:
                self._pending[provider] = path
                if provider not in self._timers:
                    timer = threading.Timer(self._coalesce_seconds, self._flush, args=(provider,))
                    timer.daemon = True
                    self._timers[provider] = timer
                    timer.start()

    def _flush(self, provider: str) -> None:
        with self._lock:
            self._timers.pop(provider, None)
            path = self._pending.pop(provider, None)
            if path is None or self._stopped:
                return
        self._callback(SourceChange(provider, path, time.time()))

    def stop(self, timeout: float = 5.0) -> None:
        """Cancel pending flushes and stop the observer."""
        with self._lock:
            self._stopped = True
            timers = list(self._timers.values())
            self._timers.clear()
            self._pending.clear()
        for timer in timers:
            timer.cancel()
        observer = self._observer
        self._observer = None
        if observer is not None:
            observer.stop()
            observer.join(timeout)


class PollingReconciler:
    """Periodic scan that detects source changes exactly once per rewrite.

    State is keyed by ``(path, mtime_ns, size)``. The very first scan primes
    the baseline without emitting callbacks (startup catch-up is the daemon's
    job); afterwards both changed and newly discovered files emit one
    ``SourceChange`` each.
    """

    def __init__(
        self,
        registry: Registry,
        callback: Callable[[SourceChange], None],
        interval: float = 5.0,
    ) -> None:
        self._registry = {provider: list(patterns) for provider, patterns in registry.items()}
        self._callback = callback
        self.interval = max(0.0, float(interval))
        self._seen: dict[str, tuple[int, int]] = {}
        self._primed = False
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def scan_once(self) -> int:
        """Scan every registered glob; return how many changes were emitted."""
        with self._lock:
            priming = not self._primed
            emitted = 0
            alive: set[str] = set()
            changes: list[SourceChange] = []
            for provider, patterns in self._registry.items():
                for pattern in patterns:
                    for match in _glob.glob(str(pattern), recursive=True):
                        try:
                            stat = os.stat(match)
                        except OSError:
                            continue
                        if not os.path.isfile(match):
                            continue
                        key = str(Path(match))
                        alive.add(key)
                        signature = (stat.st_mtime_ns, stat.st_size)
                        if self._seen.get(key) == signature:
                            continue
                        self._seen[key] = signature
                        if not priming:
                            changes.append(SourceChange(provider, Path(match), time.time()))
                            emitted += 1
            # Forget deleted files so a future recreation is reported again.
            for key in [k for k in self._seen if k not in alive]:
                del self._seen[key]
            self._primed = True
        for change in changes:
            self._callback(change)
        return emitted

    def start(self) -> None:
        """Run ``scan_once`` on a daemon thread every ``interval`` seconds."""
        if self._thread is not None:
            return
        self._stop_event.clear()

        def _loop() -> None:
            while not self._stop_event.wait(max(0.1, self.interval)):
                try:
                    self.scan_once()
                except Exception:
                    # Reconciliation must never kill the daemon; the next
                    # cycle retries from the last consistent baseline.
                    continue

        thread = threading.Thread(target=_loop, name="capture-polling-reconciler", daemon=True)
        self._thread = thread
        thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the background scan thread."""
        self._stop_event.set()
        thread = self._thread
        self._thread = None
        if thread is not None:
            thread.join(timeout)
