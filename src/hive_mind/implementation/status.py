"""The project status dashboard, derived rather than typed (D001-R2).

`CURRENT-STATE.md` is written by hand and drifts. This reads the same facts
from their sources — git for HEAD and branch, the ledger for the gate table,
the Windows inventory for the classification counts — so `status` and the
document can be compared instead of trusted.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from hive_mind.implementation.validate import (
    LEDGER,
    WINDOWS,
    _gate_table_counts,
    _read,
    git_head,
)


@dataclass
class Status:
    branch: str = "?"
    head: str = "?"
    gate_done: int = 0
    gate_failing: int = 0
    gate_partial: int = 0
    legacy_owners: int = 0
    findings: list = field(default_factory=list)

    @property
    def gate_total(self) -> int:
        return self.gate_done + self.gate_failing + self.gate_partial

    @property
    def d010(self) -> str:
        return "BLOCKED" if self.gate_failing or self.gate_partial else "READY"


def _branch(root: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "branch", "--show-current"],
            capture_output=True, text=True, timeout=15, check=True,
        )
        return out.stdout.strip() or "(detached)"
    except (subprocess.SubprocessError, OSError):
        return "?"


def collect_status(root: Optional[Path] = None) -> Status:
    from hive_mind.implementation.validate import validate_documents

    if root is None:
        from hive_mind.project import resolve_project_root

        root = resolve_project_root()
    root = Path(root)
    done, failing, partial = _gate_table_counts(_read(root, LEDGER))
    windows = _read(root, WINDOWS)
    body, _, _ = windows.partition("## Resumo do gate")
    return Status(
        branch=_branch(root),
        head=git_head(root) or "?",
        gate_done=done,
        gate_failing=failing,
        gate_partial=partial,
        legacy_owners=sum(
            1 for line in body.splitlines()
            if line.startswith("|") and "**LEGACY_OWNER**" in line
        ),
        findings=validate_documents(root),
    )


def render_status(status: Status) -> str:
    lines = [
        "PROJECT STATUS DASHBOARD",
        "",
        f"  branch                {status.branch}",
        f"  HEAD                  {status.head}",
        f"  D010-G0               {status.gate_done} completos / "
        f"{status.gate_failing} falhando / {status.gate_partial} parcial "
        f"(de {status.gate_total})",
        f"  LEGACY_OWNER          {status.legacy_owners}",
        f"  D010                  {status.d010}",
        "",
    ]
    if status.findings:
        lines.append(f"  documentos: {len(status.findings)} divergência(s)")
        lines += [f"    - {f}" for f in status.findings]
    else:
        lines.append("  documentos: consistentes com o Git")
    return "\n".join(lines)
