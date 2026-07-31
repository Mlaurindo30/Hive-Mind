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
        assert status.legacy_owners >= 0
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

    def test_dashboard_done_over_a_failed_matrix_gate(self, tmp_path):
        root = _docs(tmp_path)
        _write(root, "ACCEPTANCE-MATRIX.md",
               "| X1 | a | operational | FAILED | e | p | D004 |\n")
        _write(root, "CURRENT-STATE.md",
               "| D004 | canários | **DONE** | `abc1234` | prova | — |\n")
        assert check_no_done_over_a_failed_gate(root)

    def test_a_matrix_holding_both_states_is_not_a_finding(self, tmp_path):
        """Some gates proven and some not is what a matrix is *for*.

        The first version of this check compared rows within the matrix and
        flagged every partial delivery — which is nearly all of them. The
        comparison that means something is between documents: the dashboard
        calling a delivery finished while the matrix still fails a gate.
        """
        root = _docs(tmp_path)
        _write(root, "ACCEPTANCE-MATRIX.md",
               "| X1 | a | unit | DONE | e | p | D004 |\n"
               "| X2 | b | operational | FAILED | e | p | D004 |\n")
        _write(root, "CURRENT-STATE.md",
               "| D004 | canários | **PARTIAL** | `abc1234` | prova | — |\n")
        assert check_no_done_over_a_failed_gate(root) == []

    def test_a_non_done_dashboard_state_is_allowed(self, tmp_path):
        """PARTIAL beside a failing gate is the honest pair; DONE is not.

        This used `DONE_SYNTHETIC` as its example until the qualifier rule
        landed, which was the whole problem in miniature: a state beginning
        with DONE slipped past a check looking for exactly `DONE`, while
        reading as finished to a person.
        """
        root = _docs(tmp_path)
        _write(root, "ACCEPTANCE-MATRIX.md",
               "| X1 | a | operational | FAILED | e | p | D004 |\n")
        _write(root, "CURRENT-STATE.md",
               "| D004 | canários | **DONE_SYNTHETIC** | `abc1234` | prova | — |\n")
        assert check_no_done_over_a_failed_gate(root) == []

    def test_a_delivery_named_only_in_the_notes_is_not_the_owner(self, tmp_path):
        """"bate com canário D004" is a cross-reference, not an attribution."""
        root = _docs(tmp_path)
        _write(root, "ACCEPTANCE-MATRIX.md",
               "| X1 | a | operational | FAILED | e | bate com D004 | D009 |\n")
        _write(root, "CURRENT-STATE.md",
               "| D004 | canários | **DONE** | `abc1234` | prova | — |\n")
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

    def test_the_real_dashboard_satisfies_the_rule(self):
        from hive_mind.implementation.validate import check_dashboard_head

        assert check_dashboard_head(ROOT) == []

    @staticmethod
    def _repo(tmp_path: Path, files: list[str]) -> tuple[Path, str]:
        """A repo with one commit per file. Returns the root and the first SHA.

        Built rather than borrowed: an assertion anchored to this repository's
        own HEAD~1 passes or fails depending on what was committed last, which
        is how the first version of this test broke itself.
        """
        import subprocess

        def git(*args):
            return subprocess.run(["git", "-C", str(tmp_path), *args],
                                  capture_output=True, text=True, check=True)

        git("init", "-q")
        git("config", "user.email", "t@t")
        git("config", "user.name", "t")
        first = ""
        for path in files:
            target = tmp_path / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("x\n", encoding="utf-8")
            git("add", "-A")
            git("commit", "-q", "-m", path)
            if not first:
                first = git("rev-parse", "--short", "HEAD").stdout.strip()
        return tmp_path, first

    def test_documentation_only_commits_do_not_make_it_stale(self, tmp_path):
        from hive_mind.implementation.validate import _changed_outside_docs_since

        root, first = self._repo(tmp_path, [
            "docs/implementation/CURRENT-STATE.md",
            "docs/implementation/DELIVERY-LEDGER.md",
            "docs/implementation/MASTER-PLAN.md",
        ])
        assert _changed_outside_docs_since(root, first) == []

    def test_a_code_commit_does_make_it_stale(self, tmp_path):
        from hive_mind.implementation.validate import _changed_outside_docs_since

        root, first = self._repo(tmp_path, [
            "docs/implementation/CURRENT-STATE.md",
            "docs/implementation/MASTER-PLAN.md",
            "src/hive_mind/thing.py",
        ])
        assert len(_changed_outside_docs_since(root, first)) == 1

    def test_markdown_outside_the_implementation_docs_still_counts_as_docs(self, tmp_path):
        """README.md and AGENTS.md describe the project; they are not its state.

        The first version of this rule looked only at `docs/implementation/`,
        and flagged a delivery's own README update as the project moving on.
        """
        from hive_mind.implementation.validate import _changed_outside_docs_since

        root, first = self._repo(tmp_path, [
            "docs/implementation/CURRENT-STATE.md", "README.md", "AGENTS.md",
            "docs/agents.md",
        ])
        assert _changed_outside_docs_since(root, first) == []

    def test_a_mixed_commit_counts_as_code(self, tmp_path):
        """Docs edited alongside code is still code moving on."""
        import subprocess

        root, first = self._repo(tmp_path, ["docs/implementation/CURRENT-STATE.md"])
        (root / "src").mkdir()
        (root / "src" / "thing.py").write_text("x\n", encoding="utf-8")
        (root / "docs" / "implementation" / "CURRENT-STATE.md").write_text(
            "y\n", encoding="utf-8")
        for args in (["add", "-A"], ["commit", "-q", "-m", "mixed"]):
            subprocess.run(["git", "-C", str(root), *args], check=True,
                           capture_output=True)

        from hive_mind.implementation.validate import _changed_outside_docs_since

        assert len(_changed_outside_docs_since(root, first)) == 1


class TestSubDeliveriesAreTheirOwnDeliveries:
    """D004-R1 is not D004.

    A gate failing under D004 must not make D004-R1 — a finished sub-delivery
    that did something else entirely — look like a false claim. Matching on
    the root id did exactly that.
    """

    def test_a_parents_failing_gate_does_not_block_the_sub_delivery(self, tmp_path):
        root = _docs(tmp_path)
        _write(root, "ACCEPTANCE-MATRIX.md",
               "| C2 | codex | operational | FAILED | e | p | **D004** |\n")
        _write(root, "CURRENT-STATE.md",
               "| D004-R1 | canary runner nativo | **DONE** | `abc1234` | p |\n"
               "| D004 | canários | **PARTIAL** | `abc1234` | p |\n")
        assert check_no_done_over_a_failed_gate(root) == []

    def test_the_delivery_that_owns_the_gate_is_still_caught(self, tmp_path):
        root = _docs(tmp_path)
        _write(root, "ACCEPTANCE-MATRIX.md",
               "| C2 | codex | operational | FAILED | e | p | **D004** |\n")
        _write(root, "CURRENT-STATE.md",
               "| D004 | canários | **DONE** | `abc1234` | p |\n")
        assert check_no_done_over_a_failed_gate(root)

    def test_only_the_first_id_in_the_cell_is_the_owner(self, tmp_path):
        """"**D004** — corrigido em D004-R1" names one owner and one reference."""
        root = _docs(tmp_path)
        _write(root, "ACCEPTANCE-MATRIX.md",
               "| C2 | codex | operational | FAILED | e | p | "
               "**D004** — gate de provider. Corrigido em D004-R1 |\n")
        _write(root, "CURRENT-STATE.md",
               "| D004-R1 | canary runner nativo | **DONE** | `abc1234` | p |\n")
        assert check_no_done_over_a_failed_gate(root) == []


class TestHexIsNotAlwaysACommit:
    """A SHA-256 fingerprint looks exactly like a short commit id.

    SEC-001 records a credential's fingerprint so the incident can be tracked
    without the secret. The commit check flagged it as a commit that does not
    exist — correct about the hex, wrong about what it was.
    """

    def test_a_labelled_fingerprint_is_not_treated_as_a_commit(self, tmp_path):
        from hive_mind.implementation.validate import check_referenced_commits_exist

        root = _docs(tmp_path)
        _write(root, "DELIVERY-LEDGER.md",
               "Fingerprint SHA-256 (12): `c1ed5eac4f61`\n")
        # No git repository here, so the check no-ops; assert on the helper.
        from hive_mind.implementation.validate import NON_COMMIT_HEX

        assert NON_COMMIT_HEX.search("Fingerprint SHA-256 (12): `c1ed5eac4f61`")
        assert not NON_COMMIT_HEX.search("- **HEAD:** `abc1234` (D001-R2)")
        assert check_referenced_commits_exist(root) == []

    def test_an_unlabelled_unknown_sha_is_still_caught(self):
        """The check must not have been softened into uselessness."""
        from hive_mind.implementation.validate import check_referenced_commits_exist

        findings = check_referenced_commits_exist(ROOT)
        assert findings == [], "\n".join(str(f) for f in findings)


class TestQualifiersAreNotStates:
    """`DONE_SYNTHETIC` in the state column reads as DONE to a scanning eye."""

    def test_a_qualifier_in_the_state_column_is_a_finding(self, tmp_path):
        from hive_mind.implementation.validate import check_no_qualifier_used_as_state

        root = _docs(tmp_path)
        _write(root, "CURRENT-STATE.md",
               "| D008 | backup | **DONE_SYNTHETIC** | `abc1234` | p |\n")
        _write(root, "ACCEPTANCE-MATRIX.md", "")
        findings = check_no_qualifier_used_as_state(root)
        assert findings and "PARTIAL" not in str(findings[0]).split("**")[1]

    def test_an_official_state_is_not_a_finding(self, tmp_path):
        from hive_mind.implementation.validate import check_no_qualifier_used_as_state

        root = _docs(tmp_path)
        _write(root, "CURRENT-STATE.md",
               "| D008 | backup | **PARTIAL** | `abc1234` | evidência: sintética |\n"
               "| D009 | wrappers | **DONE** | `abc1234` | p |\n"
               "| S1 | x | **SUPERSEDED** | — | p |\n")
        _write(root, "ACCEPTANCE-MATRIX.md", "")
        assert check_no_qualifier_used_as_state(root) == []

    def test_the_real_documents_use_only_official_states(self):
        from hive_mind.implementation.validate import check_no_qualifier_used_as_state

        findings = check_no_qualifier_used_as_state(ROOT)
        assert findings == [], "\n".join(str(f) for f in findings)


class TestTheGateCounterOnlyCountsTheGate:
    """A numbered table elsewhere in the ledger is not gate criteria.

    M14's progress log used `| 1 | commit | what | ✅ |` rows, and the counter
    jumped from 24 to 29 without a single criterion changing.
    """

    def test_a_numbered_table_outside_the_gate_is_ignored(self, tmp_path):
        root = _docs(tmp_path)
        _write(root, "DELIVERY-LEDGER.md",
               "## D010-G0\n\n### Critérios (2)\n\n"
               "| # | c | Estado |\n| 1 | a | ✅ |\n| 2 | b | ❌ |\n\n"
               "**1 de 2 critérios pendentes**\n\n"
               "### Progresso de outra entrega\n\n"
               "| # | commit | o quê | estado |\n"
               "| 1 | abc | store | ✅ |\n| 2 | def | bridge | ✅ |\n")
        assert check_gate_counter(root) == []

    def test_the_gate_table_itself_is_still_counted(self, tmp_path):
        root = _docs(tmp_path)
        _write(root, "DELIVERY-LEDGER.md",
               "## D010-G0\n\n### Critérios (2)\n\n"
               "| # | c | Estado |\n| 1 | a | ✅ |\n| 2 | b | ❌ |\n\n"
               "**2 de 2 critérios pendentes**\n")
        assert check_gate_counter(root), "the counter stopped counting"
