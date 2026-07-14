"""Project root resolution (F1).

Resolution order (item D.5 of the design addendum):

  1. ``--project-root`` CLI argument.
  2. ``HIVE_MIND_HOME`` environment variable.
  3. Persisted config at ``<user_config>/project-root``.
  4. Upward search requiring **2 of 3** markers in the same directory:
     ``pyproject.toml``, ``AGENTS.md``, ``config/sinapse.yaml``.
  5. Explicit error (exit 78 / ``EX_CONFIG``).

A single isolated marker is **not** sufficient. The function is
side-effect free and never silently falls back to ``cwd``.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

EX_CONFIG = 78  # sysexits.h

_MARKERS = ("pyproject.toml", "AGENTS.md", "config/sinapse.yaml")
_MIN_MATCHES = 2


def _user_config_dir() -> Path:
    """Return the user-level config directory for the current platform."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        if not base:
            base = str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "Hive-Mind"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Hive-Mind"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "hive-mind"
    return Path.home() / ".config" / "hive-mind"


def _persisted_root() -> "Path | None":
    p = _user_config_dir() / "project-root"
    if not p.is_file():
        return None
    try:
        text = p.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not text:
        return None
    candidate = Path(text)
    if not candidate.is_dir():
        return None
    return candidate.resolve()


def _ascend(start: Path) -> "Path | None":
    start = start.resolve()
    for directory in (start, *start.parents):
        present = [m for m in _MARKERS if (directory / m).is_file()]
        if len(present) >= _MIN_MATCHES:
            return directory
    return None


def resolve_project_root(
    *,
    cli_root: "str | os.PathLike[str] | None" = None,
    env: "dict[str, str] | None" = None,
    cwd: "Path | None" = None,
) -> Path:
    """Resolve the project root using the F1 priority chain.

    Raises ``ProjectRootNotFound`` with a precise diagnostic when no
    candidate can be located. Never falls back to ``cwd`` silently.
    """
    tried: "list[tuple[str, str]]" = []
    env_map = env if env is not None else os.environ

    if cli_root is not None:
        p = Path(str(cli_root)).expanduser().resolve(strict=False)
        tried.append(("cli --project-root", str(p)))
        if p.is_dir():
            return p

    env_root = env_map.get("HIVE_MIND_HOME")
    if env_root:
        p = Path(env_root).expanduser().resolve(strict=False)
        tried.append(("HIVE_MIND_HOME", str(p)))
        if p.is_dir():
            return p

    persisted = _persisted_root()
    if persisted is not None:
        return persisted
    tried.append(("persisted config", str(_user_config_dir() / "project-root")))

    start = (cwd or Path.cwd()).resolve()
    ascended = _ascend(start)
    if ascended is not None:
        return ascended
    tried.append(
        (
            "upward search (2 of 3 markers)",
            ", ".join(_MARKERS),
        )
    )

    raise ProjectRootNotFound(tried)


class ProjectRootNotFound(RuntimeError):
    """Raised when no project root can be resolved."""

    def __init__(self, tried):
        self.tried = tried
        lines = ["could not resolve project root. Tried:"]
        for label, value in tried:
            lines.append(f"  - {label}: {value}")
        super().__init__("\n".join(lines))


def add_cli_argument(parser: argparse.ArgumentParser) -> None:
    """Register the ``--project-root`` argument on an argparse parser."""
    parser.add_argument(
        "--project-root",
        type=str,
        default=None,
        help="absolute path to the Hive-Mind project root (overrides HIVE_MIND_HOME).",
    )


if __name__ == "__main__":  # pragma: no cover - smoke entry
    p = argparse.ArgumentParser(prog="hive-mind project-root")
    add_cli_argument(p)
    args = p.parse_args()
    try:
        root = resolve_project_root(cli_root=args.project_root)
    except ProjectRootNotFound as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(EX_CONFIG)
    print(str(root))
