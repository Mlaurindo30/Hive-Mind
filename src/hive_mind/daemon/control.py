r"""Authenticated control channel for the daemon (spec §15.2, §15.3).

All mutations (start/stop/restart/reload/run-job) travel here, never over
HTTP. The transport is local-only:

  - Windows: named pipe ``\\.\pipe\hive-mindd`` with a DACL that grants access
    only to the user who created it (pywin32). Other users get ACCESS_DENIED.
  - POSIX: Unix domain socket at ``state_dir/daemon.sock`` with 0o600 perms
    inside a 0o700 state_dir.

The wire protocol is one JSON object per message, newline-terminated:
``{"command": "...", "args": {...}}`` -> ``{"ok": bool, "data": {...}, "error": ...}``.

The server does not know what a command *means*; it delegates to an injected
``dispatch`` callable. That keeps the transport testable and the managed
operations (D008 fatia 2) separate from the channel.
"""
from __future__ import annotations

import json
import socket
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

PIPE_NAME = r"\\.\pipe\hive-mindd"
SOCKET_FILENAME = "daemon.sock"
_MAX_MESSAGE_BYTES = 1 << 20  # 1 MiB ceiling on a control message


@dataclass
class ControlRequest:
    command: str
    args: dict = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps({"command": self.command, "args": self.args})

    @classmethod
    def from_json(cls, raw: str) -> "ControlRequest":
        obj = json.loads(raw)
        return cls(command=obj["command"], args=obj.get("args") or {})


@dataclass
class ControlResponse:
    ok: bool
    data: dict = field(default_factory=dict)
    error: Optional[str] = None

    def to_json(self) -> str:
        return json.dumps({"ok": self.ok, "data": self.data, "error": self.error})

    @classmethod
    def from_json(cls, raw: str) -> "ControlResponse":
        obj = json.loads(raw)
        return cls(ok=obj["ok"], data=obj.get("data") or {}, error=obj.get("error"))


Dispatch = Callable[[ControlRequest], ControlResponse]


# ---------------------------------------------------------------------------
# POSIX transport (Unix domain socket)
# ---------------------------------------------------------------------------
class _PosixControlServer:
    def __init__(self, state_dir: Path, dispatch: Dispatch) -> None:
        self.state_dir = state_dir
        self.dispatch = dispatch
        self.sock_path = state_dir / SOCKET_FILENAME
        self._server: Optional[socket.socket] = None
        self._ready = threading.Event()
        self._stop = threading.Event()

    def start(self) -> None:
        import os

        self.state_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.state_dir, 0o700)
        if self.sock_path.exists():
            self.sock_path.unlink()
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(self.sock_path))
        os.chmod(self.sock_path, 0o600)
        server.listen(8)
        server.settimeout(0.5)
        self._server = server
        self._ready.set()

    def wait_ready(self, timeout: float = 5.0) -> None:
        if not self._ready.wait(timeout):
            raise TimeoutError("control server did not become ready")

    def serve_forever(self) -> None:
        assert self._server is not None
        while not self._stop.is_set():
            try:
                conn, _ = self._server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with conn:
                _handle_stream(conn, self.dispatch)

    def shutdown(self) -> None:
        self._stop.set()
        if self._server is not None:
            self._server.close()
            self._server = None
        if self.sock_path.exists():
            try:
                self.sock_path.unlink()
            except OSError:
                pass


class _PosixControlClient:
    def __init__(self, state_dir: Path) -> None:
        self.sock_path = state_dir / SOCKET_FILENAME

    def request(self, req: ControlRequest, timeout: float = 5.0) -> ControlResponse:
        if not self.sock_path.exists():
            raise ConnectionError(f"control socket not found at {self.sock_path}")
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(timeout)
        try:
            client.connect(str(self.sock_path))
        except OSError as exc:
            raise ConnectionError(f"cannot connect to control socket: {exc}") from exc
        with client:
            client.sendall((req.to_json() + "\n").encode("utf-8"))
            return ControlResponse.from_json(_read_line(client))


# ---------------------------------------------------------------------------
# Windows transport (named pipe with per-user DACL)
# ---------------------------------------------------------------------------
class _WindowsControlServer:
    def __init__(self, state_dir: Path, dispatch: Dispatch) -> None:
        self.state_dir = state_dir
        self.dispatch = dispatch
        self._ready = threading.Event()
        self._stop = threading.Event()
        self._sa = None

    def _security_attributes(self):
        """DACL granting full control only to the current user (spec §15.3).

        The user's SID is set as owner AND as the single DACL ACE with
        GENERIC_ALL, so only the account that created the pipe can open it;
        other users get ACCESS_DENIED.
        """
        import ntsecuritycon
        import win32api
        import win32security

        user, _, _ = win32security.LookupAccountName("", win32api.GetUserName())
        sd = win32security.SECURITY_DESCRIPTOR()
        dacl = win32security.ACL()
        dacl.AddAccessAllowedAce(
            win32security.ACL_REVISION, ntsecuritycon.GENERIC_ALL, user
        )
        sd.SetSecurityDescriptorOwner(user, False)
        sd.SetSecurityDescriptorDacl(1, dacl, 0)
        sa = win32security.SECURITY_ATTRIBUTES()
        sa.SECURITY_DESCRIPTOR = sd
        return sa

    def _create_pipe(self):
        import win32pipe

        return win32pipe.CreateNamedPipe(
            PIPE_NAME,
            win32pipe.PIPE_ACCESS_DUPLEX,
            win32pipe.PIPE_TYPE_MESSAGE
            | win32pipe.PIPE_READMODE_MESSAGE
            | win32pipe.PIPE_WAIT,
            win32pipe.PIPE_UNLIMITED_INSTANCES,
            _MAX_MESSAGE_BYTES,
            _MAX_MESSAGE_BYTES,
            200,  # default timeout ms
            self._sa,
        )

    def start(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._sa = self._security_attributes()
        # Create the first pipe instance now so a client can connect the moment
        # wait_ready returns; without this there is a startup race.
        self._pending = self._create_pipe()
        self._ready.set()

    def wait_ready(self, timeout: float = 5.0) -> None:
        if not self._ready.wait(timeout):
            raise TimeoutError("control server did not become ready")

    def serve_forever(self) -> None:
        import pywintypes
        import win32file
        import win32pipe

        while not self._stop.is_set():
            handle = self._pending
            try:
                try:
                    win32pipe.ConnectNamedPipe(handle, None)
                except pywintypes.error:
                    win32file.CloseHandle(handle)
                    self._pending = self._create_pipe()
                    continue
                if self._stop.is_set():
                    win32file.CloseHandle(handle)
                    break
                self._handle_pipe(handle)
            finally:
                try:
                    win32pipe.DisconnectNamedPipe(handle)
                    win32file.CloseHandle(handle)
                except Exception:  # noqa: BLE001
                    pass
            # Ready the next instance before looping back to accept again.
            if not self._stop.is_set():
                self._pending = self._create_pipe()

    def _handle_pipe(self, handle) -> None:
        import win32file

        try:
            _, raw = win32file.ReadFile(handle, _MAX_MESSAGE_BYTES)
            line = raw.decode("utf-8").strip()
            response = _dispatch_line(line, self.dispatch)
            win32file.WriteFile(handle, (response.to_json() + "\n").encode("utf-8"))
        except Exception:  # noqa: BLE001 - one bad client must not kill the server
            pass

    def shutdown(self) -> None:
        self._stop.set()
        # Unblock the pending ConnectNamedPipe with a throwaway connection.
        try:
            import win32file

            h = win32file.CreateFile(
                PIPE_NAME,
                win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                0, None, win32file.OPEN_EXISTING, 0, None,
            )
            win32file.CloseHandle(h)
        except Exception:  # noqa: BLE001
            pass


class _WindowsControlClient:
    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir

    def request(self, req: ControlRequest, timeout: float = 5.0) -> ControlResponse:
        import time

        import pywintypes
        import win32file
        import win32pipe

        deadline = time.monotonic() + timeout
        handle = None
        last_exc: Optional[Exception] = None
        while time.monotonic() < deadline:
            try:
                win32pipe.WaitNamedPipe(PIPE_NAME, 200)
                handle = win32file.CreateFile(
                    PIPE_NAME,
                    win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                    0, None, win32file.OPEN_EXISTING, 0, None,
                )
                break
            except pywintypes.error as exc:
                last_exc = exc
                time.sleep(0.05)
        if handle is None:
            raise ConnectionError(f"cannot connect to control pipe: {last_exc}")
        try:
            win32pipe.SetNamedPipeHandleState(
                handle, win32pipe.PIPE_READMODE_MESSAGE, None, None
            )
            win32file.WriteFile(handle, (req.to_json() + "\n").encode("utf-8"))
            _, raw = win32file.ReadFile(handle, _MAX_MESSAGE_BYTES)
            return ControlResponse.from_json(raw.decode("utf-8").strip())
        finally:
            win32file.CloseHandle(handle)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
def _read_line(conn: socket.socket) -> str:
    chunks = []
    total = 0
    while True:
        chunk = conn.recv(4096)
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > _MAX_MESSAGE_BYTES or b"\n" in chunk:
            break
    return b"".join(chunks).decode("utf-8").strip()


def _dispatch_line(line: str, dispatch: Dispatch) -> ControlResponse:
    try:
        request = ControlRequest.from_json(line)
    except (json.JSONDecodeError, KeyError) as exc:
        return ControlResponse(ok=False, error=f"malformed request: {exc}")
    try:
        return dispatch(request)
    except Exception as exc:  # noqa: BLE001 - dispatch errors become clean responses
        return ControlResponse(ok=False, error=f"dispatch error: {exc}")


def _handle_stream(conn: socket.socket, dispatch: Dispatch) -> None:
    line = _read_line(conn)
    response = _dispatch_line(line, dispatch)
    conn.sendall((response.to_json() + "\n").encode("utf-8"))


# ---------------------------------------------------------------------------
# Public factory objects
# ---------------------------------------------------------------------------
def ControlServer(state_dir: Path | str, dispatch: Dispatch):
    state_dir = Path(state_dir)
    if sys.platform == "win32":
        return _WindowsControlServer(state_dir, dispatch)
    return _PosixControlServer(state_dir, dispatch)


def ControlClient(state_dir: Path | str):
    state_dir = Path(state_dir)
    if sys.platform == "win32":
        return _WindowsControlClient(state_dir)
    return _PosixControlClient(state_dir)
