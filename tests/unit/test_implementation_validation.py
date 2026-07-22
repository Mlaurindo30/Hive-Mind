"""D001-R2 — the living documents must agree with the repository.

Two kinds of test here. The first is the one that matters day to day: the
real documents, checked against the real repository, so drift becomes a red
test instead of something a reader has to catch. The rest prove each check
actually detects the drift it claims to — a validator that passes because it
looks at nothing is worse than none.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from hive_mind.implementation.status import collect_status, render_status
from hive_mind.implementation.validate import (
    check_gate_counter,
    check_internal_links,
    check_no_done_over_a_failed_gate,
    check_no_stale_canary_claims,
    check_single_head_per_document,
    check_windows_counts,
    validate_documents,
)

ROOT = Path(__file__).resolve().parents[2]


def _docs(tmp_path: Path) -> Path:
    (tmp_path / "docs" / "implementation").mkdir(parents=True)
    return tmp_path


def _write(root: Path, name: str, text: str) -> None:
    (root / "docs" / "implementation" / name).write_text(text, encoding="utf-8")


class TestTheRealDocuments:
    def test_documents_agree_with_the_repository(self):
        findings = validate_documents(ROOT)
        assert findings == [], "\n".join(str(f) for f in findings)

    def test_status_reports_the_real_gate(self):
        status = collect_status(ROOT)
        assert status.gate_total > 0
        assert status.legacy_owners > 0
        # D010 stays blocked while any criterion is outstanding.
        assert status.d010 == ("BLOCKED" if status.gate_failing or status.gate_partial
                               else "READY")

    def test_status_renders_without_the_repository_open(self):
        text = render_status(collect_status(ROOT))
        assert "PROJECT STATUS DASHBOARD" in text
        assert "D010" in text


class TestChecksDetectTheDriftTheyClaim:
    def test_two_heads_in_one_document_is_a_finding(self, tmp_path):
        root = _docs(tmp_path)
        _write(root, "CURRENT-STATE.md", "- HEAD: `aaaaaaa`\n\n- HEAD: `bbbbbbb`\n")
        _write(root, "MASTER-PLAN.md", "")
        assert check_single_head_per_document(root)

    def test_one_head_is_not_a_finding(self, tmp_path):
        root = _docs(tmp_path)
        _write(root, "CURRENT-STATE.md", "- HEAD: `aaaaaaa`\n\nmore text\n")
        _write(root, "MASTER-PLAN.md", "")
        assert check_single_head_per_document(root) == []

    def test_a_hand_typed_gate_counter_is_a_finding(self, tmp_path):
        root = _docs(tmp_path)
        _write(root, "DELIVERY-LEDGER.md",
               "## D010-G0\n\n| # | c | Estado |\n"
               "| 1 | a | ✅ |\n| 2 | b | ❌ |\n| 3 | c | ❌ |\n\n"
               "**1 de 3 critérios pendentes**\n")
        assert check_gate_counter(root)

    def test_a_derived_gate_counter_passes(self, tmp_path):
        root = _docs(tmp_path)
        _write(root, "DELIVERY-LEDGER.md",
               "## D010-G0\n\n| # | c | Estado |\n"
               "| 1 | a | ✅ |\n| 2 | b | ❌ |\n| 3 | c | ❌ |\n\n"
               "**2 de 3 critérios pendentes**\n")
        assert check_gate_counter(root) == []

    def test_a_hand_typed_windows_count_is_a_finding(self, tmp_path):
        root = _docs(tmp_path)
        _write(root, "WINDOWS-NATIVE-MIGRATION.md",
               "| a.ps1 | x | **LEGACY_OWNER** |\n"
               "| b.ps1 | x | **LEGACY_OWNER** |\n"
               "## Resumo do gate\n\n| LEGACY_OWNER (x) | **7** |\n")
        assert check_windows_counts(root)

    def test_a_stale_canary_claim_is_a_finding(self, tmp_path):
        root = _docs(tmp_path)
        _write(root, "CURRENT-STATE.md", "10 canários de providers passando\n")
        _write(root, "ACCEPTANCE-MATRIX.md", "")
        _write(root, "MASTER-PLAN.md", "")
        assert check_no_stale_canary_claims(root)

    def test_a_broken_link_is_a_finding(self, tmp_path):
        root = _docs(tmp_path)
        _write(root, "CURRENT-STATE.md", "see [gone](nowhere.md)\n")
        assert check_internal_links(root)

    def test_done_beside_a_failed_gate_of_the_same_delivery(self, tmp_path):
        root = _docs(tmp_path)
        _write(root, "ACCEPTANCE-MATRIX.md",
               "| X1 | a | unit | DONE | e | p | D004 |\n"
               "| X2 | b | operational | FAILED | e | p | D004 |\n")
        assert check_no_done_over_a_failed_gate(root)

    def test_a_qualified_done_beside_a_failed_gate_is_allowed(self, tmp_path):
        """DONE_SYNTHETIC says what was not proven; plain DONE does not."""
        root = _docs(tmp_path)
        _write(root, "ACCEPTANCE-MATRIX.md",
               "| X1 | a | unit | DONE_SYNTHETIC | e | p | D004 |\n"
               "| X2 | b | operational | FAILED | e | p | D004 |\n")
        assert check_no_done_over_a_failed_gate(root) == []

    def test_a_delivery_named_only_in_the_notes_is_not_the_owner(self, tmp_path):
        """"bate com canário D004" is a cross-reference, not an attribution."""
        root = _docs(tmp_path)
        _write(root, "ACCEPTANCE-MATRIX.md",
               "| X1 | a | unit | DONE | e | bate com canário D004 | D009 |\n"
               "| X2 | b | operational | FAILED | e | p | D004 |\n")
        assert check_no_done_over_a_failed_gate(root) == []


class TestValidateIsUsableOutsideARepository:
    def test_missing_documents_do_not_crash(self, tmp_path):
        assert validate_documents(_docs(tmp_path)) is not None


class TestDashboardHeadIsSatisfiable:
    """The rule must be one the dashboard can actually meet.

    Requiring the dashboard to name the commit that writes it is impossible:
    the SHA does not exist until the write is committed. So the dashboard may
    lag by documentation-only commits — and must not lag by anything else.
    """

    def test_lagging_by_a_docs_only_commit_is_allowed(self):
        from hive_mind.implementation.validate import (
            _changed_outside_docs_since,
            check_dashboard_head,
        )

        assert check_dashboard_head(ROOT) == []
        # The claim above is only meaningful if the helper it relies on works.
        assert _changed_outside_docs_since(ROOT, "HEAD") == []

    def test_a_code_commit_since_the_dashboard_is_a_finding(self):
        """HEAD~1 predates this delivery's code, so the helper must see it."""
        from hive_mind.implementation.validate import _changed_outside_docs_since

        assert _changed_outside_docs_since(ROOT, "HEAD~1") != []
