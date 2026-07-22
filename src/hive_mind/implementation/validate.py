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
def _is_documentation(path: str) -> bool:
    """Whether a changed path is documentation rather than project state.

    Any Markdown file counts, not only `docs/implementation/**`. The narrower
    rule flagged a commit that updated README.md and AGENTS.md as if the
    project had moved on — it had not; the same delivery was being written
    down in the places that describe it to users.
    """
    return path.endswith(".md") or path.startswith("docs/")


def _changed_outside_docs_since(root: Path, since: str) -> list[str]:
    """Commits after `since` that changed project state, not just its description.

    A documentation-only commit cannot invalidate the state the documents
    describe — it *is* the documents. Requiring the dashboard to name the
    commit that writes it would be unsatisfiable: the SHA does not exist until
    after the write.
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
        elif not _is_documentation(line):
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


# A hex string in backticks is usually a commit, but not always: a SHA-256
# fingerprint, a blob id or a content digest look identical and are not
# history. Lines that say what the value is are taken at their word.
NON_COMMIT_HEX = re.compile(
    r"fingerprint|sha-?256|digest|blob|checksum|hash", re.IGNORECASE)


def check_referenced_commits_exist(root: Path) -> list[Finding]:
    """A document must not cite a commit that is not in the history."""
    known = _known_commits(root)
    if not known:
        return []
    findings = []
    for relative in (CURRENT_STATE, MASTER_PLAN, LEDGER, MATRIX):
        seen: set[str] = set()
        for line in _read(root, relative).splitlines():
            if NON_COMMIT_HEX.search(line):
                continue
            for match in SHA_PATTERN.finditer(line):
                sha = match.group(1)
                if len(sha) < 7 or sha in seen:
                    continue
                seen.add(sha)
                if not any(k.startswith(sha) or sha.startswith(k) for k in known):
                    findings.append(Finding(
                        "unknown-commit",
                        f"{relative.name} cites `{sha}`, not in history"))
    return findings


def _gate_section(text: str) -> str:
    """Just the D010-G0 criteria section.

    Counting numbered rows across the whole ledger was wrong the moment any
    other delivery wrote a numbered table with tick marks — which M14's
    progress log did, and the counter jumped from 24 to 29 without a single
    gate criterion changing.
    """
    start = text.find("### Critérios")
    if start == -1:
        return text
    end = text.find("\n### ", start + 1)
    return text[start:end if end != -1 else len(text)]


def _gate_table_counts(text: str) -> tuple[int, int, int]:
    """Count ✅ / ❌ / ⚠️ rows in the D010-G0 criteria table."""
    done = failing = partial = 0
    for line in _gate_section(text).splitlines():
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
    """A *delivery* must not be DONE while one of its gates is FAILED.

    The comparison is between two documents, not within one. A matrix row
    saying DONE beside another row saying FAILED is a matrix doing its job —
    partial deliveries have some gates proven and some not. What must never
    happen is the dashboard calling the delivery finished while the matrix
    still records a failing gate for it.

    A qualified state (DONE_SYNTHETIC, DONE_TEMP_CONFIG, DONE_UNIT, PARTIAL)
    is fine: it names what was not proven. Unqualified DONE is not.
    """
    failed: set[str] = set()
    for line in _read(root, MATRIX).splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip().strip("*") for c in line.split("|")]
        if not any(c.split()[0:1] and c.split()[0] == "FAILED" for c in cells):
            continue
        # Attribution is the last cell. A delivery named in the notes column
        # ("bate com canário D004") is a cross-reference, not an owner.
        attribution = next((c for c in reversed(cells) if c), "")
        # The owner is the *first* id in the cell; anything after it is
        # explanation ("**D004** - gate de provider. Corrigido em D004-R1:
        # ..."). Reading every id made a delivery merely mentioned in the
        # prose answer for a gate it does not own.
        #
        # Exact ids, not roots: D004-R1 ("port the canary runner") is a
        # different delivery from D004 ("provider canaries"). The port is
        # finished; the canaries it now runs honestly are not.
        owner = DELIVERY_ID.search(attribution)
        if owner:
            failed.add(owner.group(0))
    if not failed:
        return []

    findings = []
    for line in _read(root, CURRENT_STATE).splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip().strip("*") for c in line.split("|")]
        if len(cells) < 3:
            continue
        delivery = DELIVERY_ID.search(cells[1] or "")
        if not delivery:
            continue
        state = next((c for c in cells if c.strip("*") == "DONE"), None)
        if state and delivery.group(0) in failed:
            findings.append(Finding(
                "done-over-failed",
                f"the dashboard calls {delivery.group(0)} DONE while the "
                "acceptance matrix records a FAILED gate for it",
            ))
    return findings


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



# The only states a delivery or gate may be in. Anything else is a qualifier
# describing the evidence, and belongs in the evidence column.
OFFICIAL_STATES = frozenset({
    "NOT_STARTED", "IN_PROGRESS", "PARTIAL", "BLOCKED", "FAILED", "DONE",
    "SUPERSEDED",
})

STATE_TOKEN = re.compile(r"\*\*([A-Z][A-Z_]{3,})\*\*")


def check_no_qualifier_used_as_state(root: Path) -> list[Finding]:
    """A qualifier must not stand in for a state.

    `DONE_SYNTHETIC` looked informative and was not: it hid a PARTIAL behind a
    word starting with DONE, and a reader scanning the state column saw a
    finished delivery. The qualifier is real information — it just belongs
    beside the evidence, not in place of the verdict.
    """
    findings = []
    for relative in (CURRENT_STATE, MATRIX):
        for number, line in enumerate(_read(root, relative).splitlines(), start=1):
            if not line.startswith("|"):
                continue
            for match in STATE_TOKEN.finditer(line):
                token = match.group(1)
                if token in OFFICIAL_STATES or "_" not in token:
                    continue
                root_state = token.split("_")[0]
                if root_state in OFFICIAL_STATES:
                    findings.append(Finding(
                        "qualifier-as-state",
                        f"{relative.name}:{number} uses **{token}** as a state; "
                        f"the state is **{root_state}** and the rest is evidence",
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
    check_no_qualifier_used_as_state,
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
