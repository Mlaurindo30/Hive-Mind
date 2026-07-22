"""Find where a known secret has spread, without ever showing it (SEC-001).

The awkward part of investigating a leaked credential is that the obvious
tools make it worse. `git grep <key>` and `git log -S <key>` put the secret in
a shell command line, which lands in shell history, in process listings, and
in whatever captures the session. A scanner that prints matches with context
does the same thing again, in the report meant to help.

So this reads the secret from the file that holds it, keeps it in memory, and
reports only a fingerprint and a location. The value is never written to
stdout, never passed as an argument, never included in an exception message.

The fingerprint is a truncated SHA-256 of the secret. It is enough to confirm
two findings are the same credential, and useless for recovering it.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Optional

# Files that would make a scan pathologically slow and cannot plausibly be
# where a credential was leaked *to* by this project's own work.
SKIP_DIRECTORIES = {
    ".venv", "node_modules", "__pycache__", ".mypy_cache", ".ruff_cache",
    "site-packages", ".idea", ".vs",
}

# Extensions worth reading as text. Binaries are checked as bytes anyway.
MAX_FILE_BYTES = 40 * 1024 * 1024


@dataclass(frozen=True)
class Finding:
    """Where a secret was found. Deliberately carries no excerpt."""

    fingerprint: str
    location: str
    kind: str          # working-tree | staged | commit | git-object
    detail: str = ""   # line number, blob path — never content
    tracked: Optional[bool] = None

    def __str__(self) -> str:  # pragma: no cover - display only
        state = ""
        if self.tracked is not None:
            state = " [tracked]" if self.tracked else " [untracked]"
        where = f"{self.location}{':' + self.detail if self.detail else ''}"
        return f"{self.fingerprint}  {self.kind:<12} {where}{state}"


def fingerprint(secret: str) -> str:
    """A short SHA-256 prefix. Identifies the secret; does not reveal it."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()[:12]


def read_secrets_from_settings(path: Path, *, keys: Iterable[str]) -> dict[str, str]:
    """Load named values from a JSON settings file, into memory only.

    Returns a mapping of key name to value. The caller is expected to pass the
    values to `scan` and nothing else — in particular not to a logger.
    """
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return {}
    env = data.get("env") if isinstance(data.get("env"), dict) else data
    found = {}
    for key in keys:
        value = env.get(key)
        if isinstance(value, str) and value.strip():
            found[key] = value.strip()
    return found


def _iter_files(root: Path) -> Iterator[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRECTORIES for part in path.parts):
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        yield path


def _tracked_paths(root: Path) -> set[str]:
    try:
        out = subprocess.run(["git", "-C", str(root), "ls-files"],
                             capture_output=True, text=True, timeout=60,
                             check=True)
    except (subprocess.SubprocessError, OSError):
        return set()
    return {line.strip() for line in out.stdout.splitlines() if line.strip()}


def _scan_file(path: Path, needles: dict[str, bytes], root: Path,
               tracked: set[str]) -> list[Finding]:
    try:
        blob = path.read_bytes()
    except OSError:
        return []
    findings = []
    for print_, needle in needles.items():
        if needle not in blob:
            continue
        # Locate the line without ever slicing the secret into the output.
        line_no = blob[:blob.index(needle)].count(b"\n") + 1
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError:
            relative = str(path)
        findings.append(Finding(
            fingerprint=print_,
            location=relative,
            kind="working-tree",
            detail=f"line {line_no}",
            tracked=relative in tracked,
        ))
    return findings


def _git_objects(root: Path, needles: dict[str, bytes], *,
                 max_seconds: float = 600.0) -> tuple[list[Finding], int, int]:
    """Search every reachable blob, without the secret touching a command line.

    `git cat-file --batch-all-objects --batch` streams the whole object store
    in one pass. Writing each sha to a pipe and reading its reply back was
    correct but spent all its time on round trips — this repository has enough
    objects that the difference is minutes versus hours.

    The secret never leaves this process: matching happens in Python, and no
    value is ever passed as an argument.
    """
    import time as _time

    started = _time.monotonic()
    findings: list[Finding] = []
    try:
        proc = subprocess.Popen(
            ["git", "-C", str(root), "cat-file", "--batch-all-objects",
             "--batch", "--buffer"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=1 << 20)
    except OSError:
        return findings, 0, 0

    examined = 0
    seen = 0
    try:
        stream = proc.stdout
        while True:
            if _time.monotonic() - started > max_seconds:
                break
            header = stream.readline()
            if not header:
                break
            parts = header.decode("utf-8", "replace").split()
            if len(parts) != 3:
                continue
            sha, kind, size = parts[0], parts[1], int(parts[2])
            payload = stream.read(size)
            stream.read(1)  # trailing newline
            seen += 1
            if kind != "blob":
                continue
            examined += 1
            for print_, needle in needles.items():
                if needle in payload:
                    findings.append(Finding(
                        fingerprint=print_, location=f"blob {sha[:12]}",
                        kind="git-object"))
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            proc.kill()
    return findings, examined, seen


def _staged(root: Path, needles: dict[str, bytes]) -> list[Finding]:
    try:
        diff = subprocess.run(["git", "-C", str(root), "diff", "--cached"],
                              capture_output=True, timeout=120, check=True)
    except (subprocess.SubprocessError, OSError):
        return []
    return [Finding(print_, "<staged diff>", "staged")
            for print_, needle in needles.items() if needle in diff.stdout]


def _commit_messages(root: Path, needles: dict[str, bytes]) -> list[Finding]:
    try:
        log = subprocess.run(
            ["git", "-C", str(root), "log", "--all", "--format=%H%x00%B%x00"],
            capture_output=True, timeout=300, check=True)
    except (subprocess.SubprocessError, OSError):
        return []
    findings = []
    chunks = log.stdout.split(b"\x00")
    for index in range(0, len(chunks) - 1, 2):
        sha, body = chunks[index].strip(), chunks[index + 1]
        for print_, needle in needles.items():
            if needle in body:
                findings.append(Finding(
                    print_, sha.decode("ascii", "replace")[:12],
                    "commit", "message"))
    return findings


def scan(secrets: Iterable[str], *, roots: Iterable[Path],
         repository: Optional[Path] = None) -> list[Finding]:
    """Look for each secret. Returns locations, never content."""
    needles = {fingerprint(s): s.encode("utf-8") for s in secrets if s}
    if not needles:
        return []

    findings: list[Finding] = []
    tracked = _tracked_paths(repository) if repository else set()
    for root in roots:
        root = Path(root)
        if not root.exists():
            continue
        for path in _iter_files(root):
            findings.extend(_scan_file(path, needles, root, tracked))

    if repository is not None:
        findings.extend(_staged(repository, needles))
        findings.extend(_commit_messages(repository, needles))
        object_findings, _, _ = _git_objects(repository, needles)
        findings.extend(object_findings)
    return findings


def render(findings: list[Finding], *, checked: int) -> str:
    """A report safe to paste anywhere."""
    if not findings:
        return (f"{checked} secret(s) checked — no occurrence found in any "
                "scanned location.\nThe credential is still compromised if it "
                "was ever displayed; rotation remains required.")
    lines = [f"{len(findings)} occurrence(s) of {checked} checked secret(s):", ""]
    lines += [f"  {finding}" for finding in findings]
    tracked = [f for f in findings if f.tracked]
    persisted = [f for f in findings if f.kind in {"commit", "git-object", "staged"}]
    lines.append("")
    if tracked or persisted:
        lines.append("CRITICAL: the secret is in version-controlled material.")
        lines.append("Do not rewrite history without authorisation.")
    else:
        lines.append("All occurrences are in untracked working-tree files.")
    return "\n".join(lines)
