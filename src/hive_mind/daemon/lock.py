"""Single-instance lock for hive-mindd (spec Anexo D.2).

Exactly one daemon per host, via exactly one mechanism per platform:

  - Windows: named mutex ``Local\\Hive-Mind\\hive-mindd`` (CreateMutexW).
  - Linux/macOS: ``flock(LOCK_EX | LOCK_NB)`` on ``state_dir/daemon.lock``.

A second acquisition fails fast with :class:`SingleInstanceLockError`. The
lock is advisory and process-scoped: releasing (or process exit) frees it.
This module holds the lock only; it never starts a process or mutates the
manifest.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import TracebackType


class SingleInstanceLockError(RuntimeError):
    """Raised when another hive-mindd instance already holds the lock."""


# Win32 kernel object names allow exactly one backslash, right after the
# ``Local\`` / ``Global\`` namespace prefix. The spec's literal
# ``Local\Hive-Mind\hive-mindd`` has two and fails with ERROR_PATH_NOT_FOUND (3),
# so the segments after the prefix are joined with a dash.
_MUTEX_NAME = "Local\\Hive-Mind-hive-mindd"
_ERROR_ALREADY_EXISTS = 183  # winerror.ERROR_ALREADY_EXISTS


class _WindowsLock:
    def __init__(self) -> None:
        self._handle = None

    def acquire(self) -> None:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.argtypes = [
            wintypes.LPVOID,
            wintypes.BOOL,
            wintypes.LPCWSTR,
        ]
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        handle = kernel32.CreateMutexW(None, True, _MUTEX_NAME)
        last_error = kernel32.GetLastError()
        if not handle:
            raise SingleInstanceLockError(
                f"could not create the hive-mindd instance mutex (error {last_error})"
            )
        if last_error == _ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(handle)
            raise SingleInstanceLockError(
                "another hive-mindd instance is already running (named mutex held)"
            )
        self._handle = handle

    def release(self) -> None:
        if self._handle is not None:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            kernel32.ReleaseMutex(self._handle)
            kernel32.CloseHandle(self._handle)
            self._handle = None


class _PosixLock:
    def __init__(self, lock_path: Path) -> None:
        self._lock_path = lock_path
        self._fd = None

    def acquire(self) -> None:
        import fcntl

        fd = open(self._lock_path, "w", encoding="utf-8")
        try:
            fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            fd.close()
            raise SingleInstanceLockError(
                "another hive-mindd instance is already running "
                f"(lock held on {self._lock_path})"
            ) from exc
        fd.write(str(__import__("os").getpid()))
        fd.flush()
        self._fd = fd

    def release(self) -> None:
        if self._fd is not None:
            import fcntl

            try:
                fcntl.flock(self._fd.fileno(), fcntl.LOCK_UN)
            finally:
                self._fd.close()
                self._fd = None


class SingleInstanceLock:
    """Host-wide single-instance guard for the daemon.

    Usage::

        with SingleInstanceLock(state_dir) as lock:
            ...  # only reached by the one live daemon
    """

    def __init__(self, state_dir: Path | str) -> None:
        self.state_dir = Path(state_dir)
        self.lock_path = self.state_dir / "daemon.lock"
        self._impl: _WindowsLock | _PosixLock | None = None

    @property
    def held(self) -> bool:
        return self._impl is not None

    def acquire(self) -> "SingleInstanceLock":
        if self._impl is not None:
            return self
        self.state_dir.mkdir(parents=True, exist_ok=True)
        impl: _WindowsLock | _PosixLock = (
            _WindowsLock() if sys.platform == "win32" else _PosixLock(self.lock_path)
        )
        impl.acquire()
        self._impl = impl
        return self

    def release(self) -> None:
        if self._impl is None:
            return
        self._impl.release()
        self._impl = None

    def __enter__(self) -> "SingleInstanceLock":
        return self.acquire()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.release()
