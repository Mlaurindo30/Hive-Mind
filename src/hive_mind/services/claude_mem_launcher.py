"""Start the installed Claude Mem worker without modifying its files or state."""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
from ctypes import Structure, byref, c_uint32, create_unicode_buffer, sizeof
import ctypes
from pathlib import Path


def _claude_mem_data_dir(root: Path | None = None) -> Path:
    """Diretório de dados do claude-mem: {ROOT}/claude-mem/data (projeto, gitignored)."""
    root = root or Path(__file__).resolve().parents[3]
    return root / "claude-mem" / "data"


def _vendored_worker(root: Path | None = None) -> Path | None:
    """Worker vendored no repositório (integrations/claude-mem), se existir.

    O claude-mem foi internalizado (2026-08-12, clone pinado v13.15.0 em
    integrations/claude-mem) para eliminar o não-determinismo de depender do
    cache de plugins global. Este caminho tem precedência sobre o cache: com o
    clone presente, o Hive-Mind roda SEMPRE a versão pinada do repositório, não
    a versão mais recente que por acaso esteja no cache de plugins do usuário.
    """
    root = root or Path(__file__).resolve().parents[3]
    vendored = root / "integrations" / "claude-mem" / "plugin" / "scripts" / "worker-wrapper.cjs"
    return vendored if vendored.is_file() else None


def worker_candidates(home: Path | None = None) -> list[Path]:
    """Return installed worker entrypoints, vendored copy first, then cache.

    Ordem: (1) clone vendored em integrations/claude-mem (determinístico);
    (2) cache de plugins global, da versão mais recente para a mais antiga.
    O cache permanece como fallback para ambientes sem o clone local.
    """
    home = home or Path.home()
    vendored = _vendored_worker()
    roots = (
        home / ".claude" / "plugins" / "cache" / "thedotmack" / "claude-mem",
        home / ".codex" / "plugins" / "cache" / "claude-mem-local" / "claude-mem",
    )
    candidates = [
        path
        for root in roots
        if root.is_dir()
        for path in root.glob("*/scripts/worker-wrapper.cjs")
        if path.is_file()
    ]
    candidates = sorted(candidates, key=lambda path: path.parent.parent.name, reverse=True)
    if vendored is not None:
        candidates.insert(0, vendored)
    return candidates


def resolve_bun() -> str | None:
    return os.environ.get("BUN_EXE") or shutil.which("bun") or shutil.which("bun.exe")


def command(home: Path | None = None) -> list[str]:
    worker = next(iter(worker_candidates(home)), None)
    if worker is None:
        raise RuntimeError("Claude Mem plugin is not installed; install it before enabling sinapse-claude-mem.")
    bun = resolve_bun()
    if bun is None:
        raise RuntimeError("Bun was not found; install the Claude Mem runtime before enabling sinapse-claude-mem.")
    # The installed wrapper keeps the worker attached in the foreground and
    # owns its shutdown tree.  The worker-service --daemon mode detaches,
    # which would leave the Supervisor with a successful but orphaned child.
    return [bun, str(worker)]


def _listener_pid(port: int) -> int | None:
    """Return the PID listening on an IPv4 TCP port, without a shell command."""
    if sys.platform != "win32":
        return None

    class _MibTcpRowOwnerPid(Structure):
        _fields_ = [
            ("state", c_uint32),
            ("local_addr", c_uint32),
            ("local_port", c_uint32),
            ("remote_addr", c_uint32),
            ("remote_port", c_uint32),
            ("owning_pid", c_uint32),
        ]

    size = c_uint32(0)
    get_table = ctypes.windll.iphlpapi.GetExtendedTcpTable
    # TCP_TABLE_OWNER_PID_LISTENER is 3; AF_INET is 2.
    if get_table(None, byref(size), False, 2, 3, 0) not in (0, 122):
        return None
    buffer = (c_uint32 * ((size.value + sizeof(c_uint32) - 1) // sizeof(c_uint32)))()
    if get_table(byref(buffer), byref(size), False, 2, 3, 0) != 0:
        return None
    count = buffer[0]
    row_offset = sizeof(c_uint32)
    raw = (c_uint32 * len(buffer)).from_buffer(buffer)
    for index in range(count):
        row = _MibTcpRowOwnerPid.from_buffer(raw, row_offset + index * sizeof(_MibTcpRowOwnerPid))
        if socket.ntohs(row.local_port & 0xFFFF) == port:
            return int(row.owning_pid)
    return None


def _process_image(pid: int) -> Path | None:
    """Read a process image path through the Windows API, without PowerShell."""
    if sys.platform != "win32":
        return None
    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    try:
        size = c_uint32(32768)
        buffer = create_unicode_buffer(size.value)
        if not ctypes.windll.kernel32.QueryFullProcessImageNameW(handle, 0, buffer, byref(size)):
            return None
        return Path(buffer.value)
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def _terminate_process_tree(pid: int) -> None:
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    subprocess.run(
        ["taskkill.exe", "/PID", str(pid), "/T", "/F"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
    )


def stop_legacy_daemon(port: int = 37700) -> bool:
    """Remove only the old detached Bun daemon from Claude Mem's reserved port.

    Claude Mem's global hook can race the logon task and start
    ``worker-service.cjs --daemon``.  That daemon is not supervised and makes
    the attached worker exit immediately.  The port is reserved for this
    integration, so a Bun listener there is the legacy instance to replace.
    """
    pid = _listener_pid(port)
    if pid is None:
        return False
    image = _process_image(pid)
    if image is None or image.name.lower() != "bun.exe":
        return False
    _terminate_process_tree(pid)
    return True


def is_provider_auth_failure(line: str) -> bool:
    """Whether a new worker-log line requires the configured local fallback."""
    normalized = line.lower()
    return (
        "auth error" in normalized
        and ("status 401" in normalized or "status 403" in normalized)
    ) or "invalid api key" in normalized


def _fallback_sync_command() -> list[str]:
    root = Path(__file__).resolve().parents[3]
    return [
        sys.executable,
        str(root / "scripts" / "setup" / "sync-claude-mem-provider.py"),
        "--fallback",
        "--no-restart",
    ]


def _new_auth_failure(log_path: Path, offset: int) -> tuple[bool, int]:
    """Read only newly appended worker logs, so old failures never retrigger."""
    try:
        size = log_path.stat().st_size
        if size < offset:
            offset = 0
        with log_path.open("r", encoding="utf-8", errors="replace") as log:
            log.seek(offset)
            lines = log.readlines()
        return any(is_provider_auth_failure(line) for line in lines), size
    except OSError:
        return False, offset


def _apply_local_fallback() -> bool:
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    result = subprocess.run(
        _fallback_sync_command(),
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
    )
    return result.returncode == 0


def _run_worker_with_fallback() -> int:
    """Keep the global worker attached and change to the local fallback on 401/403."""
    log_path = _claude_mem_data_dir() / "logs" / f"claude-mem-{time.strftime('%Y-%m-%d')}.log"
    offset = log_path.stat().st_size if log_path.exists() else 0
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    fallback_applied = False

    # P1 (2026-08-12): o claude-mem foi internalizado. NÃO herdamos a telemetria
    # PostHog do upstream (cmem.ai) — desligamos por construção, no spawn, para
    # que o worker vendored nunca envie dados a um serviço externo.
    worker_env = dict(os.environ)
    worker_env.setdefault("CLAUDE_MEM_TELEMETRY", "0")
    worker_env.setdefault("DO_NOT_TRACK", "1")
    # Dados project-local: o worker deve gravar em {ROOT}/claude-mem/data, não
    # em ~/.claude-mem. Sobrescreve qualquer valor herdado do ambiente global.
    worker_env["CLAUDE_MEM_DATA_DIR"] = str(_claude_mem_data_dir())

    while True:
        stop_legacy_daemon()
        process = subprocess.Popen(command(), creationflags=flags, env=worker_env)
        while process.poll() is None:
            auth_failure, offset = _new_auth_failure(log_path, offset)
            if auth_failure and not fallback_applied and _apply_local_fallback():
                fallback_applied = True
                _terminate_process_tree(process.pid)
                process.wait(timeout=20)
                break
            time.sleep(0.5)
        else:
            return process.returncode or 0


def main() -> int:
    try:
        return _run_worker_with_fallback()
    except RuntimeError as exc:
        print(f"claude-mem launcher: {exc}", file=sys.stderr)
        return 69


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
