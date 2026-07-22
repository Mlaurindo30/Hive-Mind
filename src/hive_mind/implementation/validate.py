"""Checks that keep the living documents honest (D001-R2).

Every check answers a question a reader would otherwise have to verify by
hand, and each one exists because the document actually drifted that way:

  - the dashboard claimed a HEAD that was not the repository's;
  - `CURRENT-STATE.md` carried two different HEADs in one file;
  - the D010-G0 summary said "5 pendentes" while its own table said otherwise;
  - the Windows inventory counts were typed rather than derived;
  - an aggregate line still claimed "10 canários passando" after the real
    canary reported 4 passed / 4 failed / 4 skipped;
  - documents referenced commits that do not exist.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

DOCS = Path("docs/implementation")
CURRENT_STATE = DOCS / "CURRENT-STATE.md"
MASTER_PLAN = DOCS / "MASTER-PLAN.md"
LEDGER = DOCS / "DELIVERY-LEDGER.md"
MATRIX = DOCS / "ACCEPTANCE-MATRIX.md"
WINDOWS = DOCS / "WINDOWS-NATIVE-MIGRATION.md"

SHA_PATTERN = re.compile(r"`([0-9a-f]{7,40})`")
CLASSIFICATIONS = (
    "NATIVE", "LEGACY_OWNER", "TO_REMOVE", "THIN_WRAPPER", "SHIM",
    "EXTERNAL_COMPONENT", "PORT_IN_PROGRESS", "UNKNOWN",
)


@dataclass(frozen=True)
class Finding:
    check: str
    detail: str

    def __str__(self) -> str:  # pragma: no cover - display only
        return f"{self.check}: {self.detail}"


def _read(root: Path, relative: Path) -> str:
    path = root / relative
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def git_head(root: Path) -> Optional[str]:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=15, check=True,
        )
        return out.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return None


def _known_commits(root: Path) -> set[str]:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "log", "--format=%h", "-400"],
            capture_output=True, text=True, timeout=30, check=True,
        )
        return {line.strip() for line in out.stdout.splitlines() if line.strip()}
    except (subprocess.SubprocessError, OSError):
        return set()


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------
def _changed_outside_docs_since(root: Path, since: str) -> list[str]:
    """Commits after `since` that touched anything but the living documents.

    A commit that only edits `docs/implementation/**` cannot invalidate the
    state those documents describe — it *is* the documents. Requiring the
    dashboard to name the commit that writes it would be unsatisfiable: the
    SHA does not exist until after the write.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "log", "--format=%h", "--name-only",
             f"{since}..HEAD"],
            capture_output=True, text=True, timeout=30, check=True,
        )
    except (subprocess.SubprocessError, OSError):
        return []
    commits, current, touched_code = [], None, False
    for line in out.stdout.splitlines() + [""]:
        line = line.strip()
        if not line:
            if current and touched_code:
                commits.append(current)
            continue
        if re.fullmatch(r"[0-9a-f]{7,40}", line):
            if current and touched_code:
                commits.append(current)
            current, touched_code = line, False
        elif not line.startswith("docs/implementation/"):
            touched_code = True
    return commits


def check_dashboard_head(root: Path) -> list[Finding]:
    """The dashboard must name the commit whose state it describes.

    Equal to HEAD is the normal case. It may also lag behind HEAD by
    documentation-only commits — those are the dashboard writing itself down,
    not project state moving on without it.
    """
    head = git_head(root)
    if head is None:
        return []
    text = _read(root, CURRENT_STATE)
    match = re.search(r"\*\*HEAD:\*\*\s*`([0-9a-f]{7,40})`", text)
    if not match:
        return [Finding("dashboard-head", "no **HEAD:** line in the dashboard")]
    claimed = match.group(1)
    if claimed.startswith(head) or head.startswith(claimed):
        return []
    stale = _changed_outside_docs_since(root, claimed)
    if not stale:
        return []
    return [Finding(
        "dashboard-head",
        f"dashboard says {claimed}; repository is at {head} with "
        f"{len(stale)} non-documentation commit(s) since: {stale}",
    )]


def check_single_head_per_document(root: Path) -> list[Finding]:
    """One document must not advertise two different HEADs."""
    findings = []
    for relative in (CURRENT_STATE, MASTER_PLAN):
        text = _read(root, relative)
        heads = {
            m.group(1)
            for m in re.finditer(r"^-\s+\*{0,2}HEAD:?\*{0,2}:?\s*`([0-9a-f]{7,40})`",
                                 text, re.M)
        }
        if len(heads) > 1:
            findings.append(Finding(
                "single-head", f"{relative.name} advertises {sorted(heads)}"
            ))
    return findings


def check_referenced_commits_exist(root: Path) -> list[Finding]:
    """A document must not cite a commit that is not in the history."""
    known = _known_commits(root)
    if not known:
        return []
    findings = []
    for relative in (CURRENT_STATE, MASTER_PLAN, LEDGER, MATRIX):
        text = _read(root, relative)
        for sha in {m.group(1) for m in SHA_PATTERN.finditer(text)}:
            if len(sha) < 7:
                continue
            if not any(k.startswith(sha) or sha.startswith(k) for k in known):
                findings.append(Finding(
                    "unknown-commit", f"{relative.name} cites `{sha}`, not in history"
                ))
    return findings


def _gate_table_counts(text: str) -> tuple[int, int, int]:
    """Count ✅ / ❌ / ⚠️ rows in the D010-G0 criteria table."""
    done = failing = partial = 0
    for line in text.splitlines():
        if not re.match(r"^\|\s*\d+\s*\|", line):
            continue
        if "✅" in line:
            done += 1
        elif "❌" in line:
            failing += 1
        elif "⚠" in line:
            partial += 1
    return done, failing, partial


def check_gate_counter(root: Path) -> list[Finding]:
    """The D010-G0 summary must be derived from its own table."""
    text = _read(root, LEDGER)
    if "D010-G0" not in text:
        return []
    done, failing, partial = _gate_table_counts(text)
    if done + failing + partial == 0:
        return [Finding("gate-counter", "D010-G0 table has no scored rows")]
    claimed = re.search(r"\*\*(\d+)\s+de\s+(\d+)\s+critérios pendentes", text)
    outstanding = failing + partial
    if not claimed:
        return [Finding("gate-counter", "D010-G0 has no summary line to verify")]
    if int(claimed.group(1)) != outstanding:
        return [Finding(
            "gate-counter",
            f"summary claims {claimed.group(1)} outstanding; table has "
            f"{outstanding} ({failing} failing + {partial} partial)",
        )]
    if int(claimed.group(2)) != done + failing + partial:
        return [Finding(
            "gate-counter",
            f"summary totals {claimed.group(2)}; table has {done + failing + partial}",
        )]
    return []


def check_windows_counts(root: Path) -> list[Finding]:
    """The Windows inventory summary must be derived from its rows."""
    text = _read(root, WINDOWS)
    if not text:
        return []
    body, _, summary = text.partition("## Resumo do gate")
    if not summary:
        return [Finding("windows-summary", "no summary section to verify")]
    actual = sum(
        1 for line in body.splitlines()
        if line.startswith("|") and "**LEGACY_OWNER**" in line
    )
    claimed = re.search(r"LEGACY_OWNER[^|]*\|\s*\*{0,2}(\d+)", summary)
    if claimed and int(claimed.group(1)) != actual:
        return [Finding(
            "windows-summary",
            f"summary says {claimed.group(1)} LEGACY_OWNER rows; table has {actual}",
        )]
    return []


def check_no_stale_canary_claims(root: Path) -> list[Finding]:
    """Aggregate claims must not contradict the real canary result.

    D004-R1's real run reported 4 passed / 4 failed / 4 skipped. Any line
    still claiming every provider passes is a leftover from the mocked era.
    """
    banned = (
        "10 canários",
        "10 canarios",
        "cadeia provada de ponta a ponta",
        "10 isolates",
    )
    findings = []
    for relative in (CURRENT_STATE, MATRIX, MASTER_PLAN):
        text = _read(root, relative)
        for phrase in banned:
            if phrase in text:
                findings.append(Finding(
                    "stale-canary-claim",
                    f"{relative.name} still claims '{phrase}'; the real canary "
                    "reported 4 passed / 4 failed / 4 skipped",
                ))
    return findings


def check_internal_links(root: Path) -> list[Finding]:
    """Every relative markdown link must resolve to a file that exists."""
    findings = []
    for relative in (CURRENT_STATE, MASTER_PLAN, LEDGER, MATRIX, WINDOWS,
                     DOCS / "README.md"):
        text = _read(root, relative)
        if not text:
            continue
        base = (root / relative).parent
        for match in re.finditer(r"\]\(([^)#:]+\.md)\)", text):
            target = (base / match.group(1)).resolve()
            if not target.is_file():
                findings.append(Finding(
                    "broken-link", f"{relative.name} -> {match.group(1)}"
                ))
    return findings


DELIVERY_ID = re.compile(r"\bD0\d{2}(?:-[A-Z]?\d?[A-Z]?)?\b")


def _ledger_deliveries(root: Path) -> set[str]:
    """Delivery ids that have a section of their own in the ledger."""
    text = _read(root, LEDGER)
    return {
        m.group(0)
        for line in text.splitlines() if line.startswith("## ")
        for m in [DELIVERY_ID.search(line)] if m
    }


def check_matrix_deliveries_are_in_the_ledger(root: Path) -> list[Finding]:
    """A delivery the matrix scores must be a delivery the ledger records.

    The matrix is where a gate is marked DONE; the ledger is where the work
    is described. A delivery that exists only in the matrix has a verdict
    without a record of what produced it.
    """
    known = _ledger_deliveries(root)
    if not known:
        return []
    text = _read(root, MATRIX)
    cited: set[str] = set()
    for line in text.splitlines():
        if line.startswith("|"):
            cited.update(DELIVERY_ID.findall(line))
    missing = sorted(
        d for d in cited
        if not any(k == d or k.startswith(d.split("-")[0]) for k in known)
    )
    return [Finding("matrix-vs-ledger", f"scored but not recorded: {missing}")] if missing else []


def check_no_done_over_a_failed_gate(root: Path) -> list[Finding]:
    """A delivery must not be plain DONE while one of its gates is FAILED.

    A qualified state (DONE_SYNTHETIC, DONE_TEMP_CONFIG, PARTIAL) is fine —
    it says what was and was not proven. Unqualified DONE is not.
    """
    text = _read(root, MATRIX)
    failed: set[str] = set()
    done: dict[str, str] = {}
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip().strip("*") for c in line.split("|")]
        state = next((c for c in cells if c.split()[0:1] and
                      c.split()[0] in {"DONE", "FAILED", "PARTIAL"}), "")
        if not state:
            continue
        # Attribution is the last cell. A delivery named in the notes column
        # ("bate com canário D004") is a cross-reference, not an owner.
        attribution = next((c for c in reversed(cells) if c), "")
        for delivery in DELIVERY_ID.findall(attribution):
            root_id = delivery.split("-")[0]
            if state.startswith("FAILED"):
                failed.add(root_id)
            elif state == "DONE":
                done[root_id] = line.strip()[:70]
    clash = sorted(failed & set(done))
    return [
        Finding("done-over-failed",
                f"{d} is marked DONE somewhere while another gate of {d} is FAILED")
        for d in clash
    ]


def check_no_not_started_for_a_closed_delivery(root: Path) -> list[Finding]:
    """A delivery the ledger closed must not still be scored NOT_STARTED."""
    ledger = _read(root, LEDGER)
    closed = {
        m.group(0)
        for line in ledger.splitlines()
        if line.startswith("## ") and ("fechamento" in line or "✅" in line)
        for m in [DELIVERY_ID.search(line)] if m
    }
    if not closed:
        return []
    findings = []
    for line in _read(root, MATRIX).splitlines():
        if not line.startswith("|") or "NOT_STARTED" not in line:
            continue
        for delivery in DELIVERY_ID.findall(line):
            if delivery in closed:
                findings.append(Finding(
                    "not-started-but-closed",
                    f"{delivery} is closed in the ledger but scored NOT_STARTED",
                ))
    return findings


CHECKS = (
    check_dashboard_head,
    check_single_head_per_document,
    check_referenced_commits_exist,
    check_gate_counter,
    check_windows_counts,
    check_no_stale_canary_claims,
    check_internal_links,
    check_matrix_deliveries_are_in_the_ledger,
    check_no_done_over_a_failed_gate,
    check_no_not_started_for_a_closed_delivery,
)


def validate_documents(root: Optional[Path] = None) -> list[Finding]:
    """Run every check. An empty list means the documents agree with reality."""
    if root is None:
        from hive_mind.project import resolve_project_root

        root = resolve_project_root()
    root = Path(root)
    findings: list[Finding] = []
    for check in CHECKS:
        findings.extend(check(root))
    return findings
