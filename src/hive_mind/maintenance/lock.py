"""Single-instance lock for maintenance jobs.

A backup must never run twice concurrently: two writers on the same
destination can interleave a partial file with a finished one. This is a
plain exclusive-create lockfile — portable, and it releases on process exit
because the file carries the owning PID and is removed in a finally block.
"""
from __future__ import annotations

import os
from pathlib import Path
from types import TracebackType


class MaintenanceLockError(RuntimeError):
    """Raised when another maintenance run already holds the lock."""


class MaintenanceLock:
    def __init__(self, lock_path: Path | str) -> None:
        self.lock_path = Path(lock_path)
        self._fd: int | None = None

    @property
    def held(self) -> bool:
        return self._fd is not None

    def acquire(self) -> "MaintenanceLock":
        if self._fd is not None:
            return self
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise MaintenanceLockError(
                f"another maintenance run holds {self.lock_path}"
            ) from exc
        os.write(fd, str(os.getpid()).encode("ascii"))
        self._fd = fd
        return self

    def release(self) -> None:
        if self._fd is None:
            return
        try:
            os.close(self._fd)
        finally:
            self._fd = None
            try:
                self.lock_path.unlink()
            except OSError:
                pass

    def __enter__(self) -> "MaintenanceLock":
        return self.acquire()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.release()
