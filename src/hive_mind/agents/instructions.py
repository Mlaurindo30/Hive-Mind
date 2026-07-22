"""Native install of the Hive-Mind agent instructions (D009-R5).

Ports `Inject-Instructions` from register-mcp.ps1: the prompt is written into
the agent's instruction file inside a managed block, so re-running replaces
the block instead of appending a second copy, and everything the user wrote
around it is left alone.

    <!-- BEGIN HIVE-MIND SINAPSE ... -->
    ...prompt...
    <!-- END HIVE-MIND SINAPSE -->

Writes follow the same transactional contract as the config writers: back up,
write a temp file on the same volume, `os.replace`. Dry-run is the default at
every call site that inspects.
"""
from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

BEGIN_MARKER = (
    "<!-- BEGIN HIVE-MIND SINAPSE (auto-managed by hive-mind -- do not edit) -->"
)
END_MARKER = "<!-- END HIVE-MIND SINAPSE -->"
# The PowerShell installer used its own name in the marker; recognise it so an
# existing block is replaced rather than duplicated alongside a new one.
LEGACY_BEGIN_MARKER = (
    "<!-- BEGIN HIVE-MIND SINAPSE (auto-managed by register-mcp.ps1 -- do not edit) -->"
)
DEFAULT_PROMPT = Path("config") / "sinapse-agent-prompt.md"


@dataclass(frozen=True)
class InstructionResult:
    provider: str
    path: str
    changed: bool
    created: bool
    backup: Optional[str] = None
    note: Optional[str] = None


def _block(prompt: str) -> str:
    return f"{BEGIN_MARKER}\n{prompt.rstrip()}\n{END_MARKER}\n"


def _managed_pattern() -> re.Pattern[str]:
    begins = "|".join(re.escape(m) for m in (BEGIN_MARKER, LEGACY_BEGIN_MARKER))
    return re.compile(
        rf"(?:{begins}).*?{re.escape(END_MARKER)}\n?", re.S
    )


def render(existing: str, prompt: str) -> str:
    """Return `existing` with the managed block inserted or replaced."""
    block = _block(prompt)
    pattern = _managed_pattern()
    if pattern.search(existing):
        return pattern.sub(lambda _: block, existing, count=1)
    prefix = existing.rstrip("\r\n")
    return f"{prefix}\n\n{block}" if prefix else block


def install_instructions(
    provider_id: str,
    target_path: Path | str,
    prompt: str,
    *,
    dry_run: bool = True,
) -> InstructionResult:
    """Install the managed instruction block into one agent's file."""
    target_path = Path(target_path)
    created = not target_path.exists()
    existing = "" if created else target_path.read_text(encoding="utf-8-sig")
    updated = render(existing, prompt)
    changed = updated != existing

    if dry_run or not changed:
        return InstructionResult(provider_id, str(target_path), changed, created)

    target_path.parent.mkdir(parents=True, exist_ok=True)
    backup: Optional[Path] = None
    if not created:
        backup = target_path.with_suffix(target_path.suffix + ".hive-bak")
        shutil.copy2(target_path, backup)

    tmp = target_path.with_suffix(target_path.suffix + ".hive-tmp")
    try:
        tmp.write_text(updated, encoding="utf-8", newline="\n")
        os.replace(tmp, target_path)
    except Exception:
        if backup is not None and backup.exists():
            shutil.copy2(backup, target_path)
        tmp.unlink(missing_ok=True)
        raise
    return InstructionResult(
        provider_id, str(target_path), True, created,
        str(backup) if backup else None,
    )


def remove_instructions(
    provider_id: str, target_path: Path | str, *, dry_run: bool = True
) -> InstructionResult:
    """Remove the managed block, leaving the user's own content intact."""
    target_path = Path(target_path)
    if not target_path.exists():
        return InstructionResult(provider_id, str(target_path), False, False,
                                 note="file absent")
    existing = target_path.read_text(encoding="utf-8-sig")
    updated = _managed_pattern().sub("", existing, count=1).rstrip("\r\n")
    updated = updated + "\n" if updated else ""
    changed = updated != existing
    if dry_run or not changed:
        return InstructionResult(provider_id, str(target_path), changed, False)

    backup = target_path.with_suffix(target_path.suffix + ".hive-bak")
    shutil.copy2(target_path, backup)
    tmp = target_path.with_suffix(target_path.suffix + ".hive-tmp")
    tmp.write_text(updated, encoding="utf-8", newline="\n")
    os.replace(tmp, target_path)
    return InstructionResult(provider_id, str(target_path), True, False, str(backup))


def has_managed_block(target_path: Path | str) -> bool:
    path = Path(target_path)
    if not path.is_file():
        return False
    return bool(_managed_pattern().search(path.read_text(encoding="utf-8-sig")))


def load_prompt(project_root: Path | str) -> str:
    path = Path(project_root) / DEFAULT_PROMPT
    if not path.is_file():
        raise FileNotFoundError(f"agent prompt not found: {path}")
    return path.read_text(encoding="utf-8-sig")
