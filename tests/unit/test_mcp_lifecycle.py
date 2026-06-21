from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SUPERVISOR = ROOT / "scripts" / "services" / "mcp-lifecycle.py"


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def test_mcp_lifecycle_proxies_stdio() -> None:
    child = (
        "import sys\n"
        "for line in sys.stdin.buffer:\n"
        "    sys.stdout.buffer.write(b'child:' + line)\n"
        "    sys.stdout.buffer.flush()\n"
    )
    proc = subprocess.run(
        [sys.executable, str(SUPERVISOR), "--", sys.executable, "-c", child],
        input=b"ping\n",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=True,
    )

    assert proc.stdout == b"child:ping\n"
    assert b"[mcp-lifecycle]" not in proc.stdout


def test_mcp_lifecycle_terminates_child_when_stdin_closes(tmp_path: Path) -> None:
    pid_file = tmp_path / "child.pid"
    child = (
        "import pathlib, sys, time, os\n"
        f"pathlib.Path({str(pid_file)!r}).write_text(str(os.getpid()))\n"
        "sys.stdout.write('ready\\n')\n"
        "sys.stdout.flush()\n"
        "time.sleep(60)\n"
    )
    proc = subprocess.Popen(
        [sys.executable, str(SUPERVISOR), "--", sys.executable, "-c", child],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert proc.stdout is not None
        assert proc.stdout.readline().strip() == "ready"
        child_pid = int(pid_file.read_text())

        assert proc.stdin is not None
        proc.stdin.close()

        code = proc.wait(timeout=10)
        assert code in (143, -signal.SIGTERM)
        assert not _pid_alive(child_pid)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
