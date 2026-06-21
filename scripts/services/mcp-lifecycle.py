#!/usr/bin/env python3
"""Stdio MCP lifecycle supervisor.

The process that a MCP client starts should die with that client. Some MCP
servers keep running after their parent agent exits, so this supervisor proxies
stdio and terminates the whole child process group when stdin closes, the parent
PID changes, or the supervisor receives SIGTERM/SIGINT.
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import threading
import time
from typing import BinaryIO


def _log(message: str) -> None:
    print(f"[mcp-lifecycle] {message}", file=sys.stderr, flush=True)


def _pump(src: BinaryIO, dst: BinaryIO | None, *, on_eof) -> None:
    try:
        while True:
            chunk = src.read(65536)
            if not chunk:
                break
            if dst is None:
                break
            dst.write(chunk)
            dst.flush()
    except BrokenPipeError:
        pass
    finally:
        on_eof()


def _terminate_group(proc: subprocess.Popen[bytes], *, reason: str) -> None:
    if proc.poll() is not None:
        return
    _log(f"terminating child pid={proc.pid}: {reason}")
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except PermissionError:
        proc.terminate()
    try:
        proc.wait(timeout=5)
        return
    except subprocess.TimeoutExpired:
        pass
    _log(f"killing child pid={proc.pid}: graceful shutdown timed out")
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    except PermissionError:
        proc.kill()
    proc.wait(timeout=5)


def _exit_code(proc: subprocess.Popen[bytes]) -> int:
    code = proc.poll()
    if code is None:
        return 143
    if code < 0:
        return 128 + abs(code)
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Proxy stdio and reap orphan MCP servers.")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)

    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("missing child command")

    original_parent = os.getppid()
    child = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=None,
        start_new_session=True,
        bufsize=0,
    )

    stdin_closed = threading.Event()
    stdout_closed = threading.Event()

    def close_child_stdin() -> None:
        stdin_closed.set()
        if child.stdin:
            try:
                child.stdin.close()
            except BrokenPipeError:
                pass

    def close_stdout() -> None:
        stdout_closed.set()

    threads = [
        threading.Thread(
            target=_pump,
            args=(sys.stdin.buffer, child.stdin),
            kwargs={"on_eof": close_child_stdin},
            daemon=True,
        ),
        threading.Thread(
            target=_pump,
            args=(child.stdout, sys.stdout.buffer),
            kwargs={"on_eof": close_stdout},
            daemon=True,
        ),
    ]
    for thread in threads:
        thread.start()

    shutdown = {"signal": None}

    def handle_signal(signum, _frame) -> None:
        shutdown["signal"] = signum
        _terminate_group(child, reason=f"signal {signum}")

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    stdin_closed_at: float | None = None
    while True:
        code = child.poll()
        if code is not None:
            return code

        if shutdown["signal"] is not None:
            return 128 + int(shutdown["signal"])

        if os.getppid() != original_parent:
            _terminate_group(child, reason=f"parent pid changed {original_parent}->{os.getppid()}")
            return 143

        if stdin_closed.is_set():
            if stdin_closed_at is None:
                stdin_closed_at = time.monotonic()
            elif time.monotonic() - stdin_closed_at >= 2.0:
                _terminate_group(child, reason="stdin closed")
                return _exit_code(child)

        time.sleep(0.1)


if __name__ == "__main__":
    raise SystemExit(main())
