"""D004-R2 — the identity rules, stated as tests.

Most of these exist because the free-label path actually produced the value
being tested against. `preciso-que-verifique-o-por-que-3` is not a made-up
example: it is a project with 37 observations in the real Claude Mem store,
created because a prompt's text reached the field Claude Mem groups by.

The tests are grouped by what they protect:

  - the label is never authority;
  - both entrypoints reach the same answer;
  - unclassified is a deliverable, deterministic answer, not a rejection;
  - invalid is rejected before anything is written;
  - there is exactly one implementation.
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from hive_mind.capture.identity import (
    apply_identity,
    resolve_identity,
    unclassified_identity,
    validate_envelope,
)
from hive_mind.capture.models import IdentityRefused, IdentityStatus
from hive_mind.projects.identity import ProjectIdentityResolver

ROOT = Path(__file__).resolve().parents[2]
CAPTURE = ROOT / "scripts" / "capture"


@pytest.fixture(scope="module")
def resolver():
    return ProjectIdentityResolver()


def _git(path: Path, *args):
    return subprocess.run(["git", "-C", str(path), *args],
                          capture_output=True, text=True, check=True)


@pytest.fixture
def repo_with_worktree(tmp_path):
    """A real repository and a real worktree of it.

    Built rather than mocked: the resolver reads git, so a fake would test the
    fake. This is the shape that produced the defect — the worktree of this
    very repository became a project separate from its root.
    """
    repo = tmp_path / "acme-service"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "README.md").write_text("x\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")

    tree = tmp_path / "acme-service-feature"
    _git(repo, "worktree", "add", "-q", "-b", "feature", str(tree))
    return repo, tree


# ---------------------------------------------------------------------------
# The parser's label is never authority
# ---------------------------------------------------------------------------
class TestTheFreeLabelIsNotAuthority:
    @pytest.mark.parametrize("label", [
        "preciso-que-verifique-o-por-que-3",
        "preciso-que-verifique-o-por-que",
        "referenced-chatgpt-conversation-this-is-untrusted",
        "shadow-run-clean",
        "ins",
        "pr",
        "miche",
        "Microsoft VS Code",
        "Qwen",
    ])
    def test_a_free_label_never_becomes_the_project(self, resolver, label):
        """Every one of these is a real value from the production store."""
        identity = resolve_identity("codex", {"sid": "s", "project": label},
                                    resolver=resolver)
        assert identity.project_name != label
        assert identity.project_id != label
        assert identity.status is IdentityStatus.UNCLASSIFIED

    def test_the_label_survives_only_as_audit(self, resolver):
        identity = resolve_identity(
            "codex", {"sid": "s", "project": "referenced-chatgpt-conversation"},
            resolver=resolver)
        session = apply_identity({"sid": "s"}, identity)

        assert session["metadata"]["capture"]["raw_project_label"] == \
            "referenced-chatgpt-conversation"
        # And nowhere that groups, filters or builds a path.
        for field in ("project", "project_id", "project_name", "workspace_id"):
            assert session.get(field) != "referenced-chatgpt-conversation"
        assert session["project_identity"].get("project_id") != \
            "referenced-chatgpt-conversation"

    def test_a_prompt_is_not_evidence(self, resolver):
        """The prompt text is not consulted at all, whatever it contains."""
        session = {"sid": "s", "prompt": "work on the acme-service repository",
                   "project": "acme-service"}
        identity = resolve_identity("codex", session, resolver=resolver)
        assert "acme" not in identity.project_id

    def test_the_surface_is_not_the_project(self, resolver):
        identity = resolve_identity("codex", {"sid": "s", "surface": "ide"},
                                    resolver=resolver)
        assert identity.project_id != "ide"
        assert "ide" not in identity.project_name.casefold().split()


# ---------------------------------------------------------------------------
# One answer, whoever asks
# ---------------------------------------------------------------------------
class TestBothEntrypointsAgree:
    def test_a_worktree_and_its_root_are_one_project(self, resolver,
                                                     repo_with_worktree):
        """The regression by name: `hive-mind-windows-zero-install`."""
        repo, tree = repo_with_worktree
        from_root = resolve_identity("codex", {"sid": "a", "cwd": str(repo)},
                                     resolver=resolver)
        from_tree = resolve_identity("codex", {"sid": "b", "cwd": str(tree)},
                                     resolver=resolver)
        assert from_root.project_id == from_tree.project_id
        assert from_root.project_name == from_tree.project_name

    def test_the_worktree_name_does_not_leak_into_the_project(
            self, resolver, repo_with_worktree):
        _, tree = repo_with_worktree
        identity = resolve_identity(
            "codex", {"sid": "b", "cwd": str(tree),
                      "project": "acme-service-feature"}, resolver=resolver)
        assert identity.project_id != "acme-service-feature"

    def test_the_same_evidence_yields_the_same_answer_for_any_provider_surface(
            self, resolver, repo_with_worktree):
        """Provider and surface are metadata, never identity."""
        repo, _ = repo_with_worktree
        a = resolve_identity("codex", {"sid": "a", "cwd": str(repo),
                                       "surface": "cli"}, resolver=resolver)
        b = resolve_identity("antigravity", {"sid": "b", "cwd": str(repo),
                                             "surface": "ide"}, resolver=resolver)
        assert a.project_id == b.project_id

    def test_resolution_is_idempotent(self, resolver, repo_with_worktree):
        """Re-ingesting an already-identified session must not drift."""
        repo, _ = repo_with_worktree
        first = resolve_identity("codex", {"sid": "a", "cwd": str(repo)},
                                 resolver=resolver)
        once = apply_identity({"sid": "a", "cwd": str(repo)}, first)
        second = resolve_identity("codex", once, resolver=resolver)
        assert second.project_id == first.project_id
        assert apply_identity(once, second)["project"] == once["project"]


# ---------------------------------------------------------------------------
# Unclassified delivers; it is not a rejection
# ---------------------------------------------------------------------------
class TestUnclassifiedIsAnAnswer:
    def test_a_session_without_git_still_delivers(self, resolver, tmp_path):
        identity = resolve_identity("codex", {"sid": "s", "cwd": str(tmp_path)},
                                    resolver=resolver)
        assert identity.deliverable
        assert identity.degraded

    def test_it_is_deterministic(self, resolver):
        a = resolve_identity("codex", {"sid": "a"}, resolver=resolver)
        b = resolve_identity("codex", {"sid": "b"}, resolver=resolver)
        assert a.project_id == b.project_id == "unclassified/codex"

    def test_it_borrows_nothing_from_the_directory_name(self, resolver, tmp_path):
        odd = tmp_path / "some-random-folder"
        odd.mkdir()
        identity = resolve_identity("codex", {"sid": "s", "cwd": str(odd)},
                                    resolver=resolver)
        assert "some-random-folder" not in identity.project_id

    def test_it_is_namespaced_by_provider(self):
        assert unclassified_identity("codex", "cli", None).project_id == \
            "unclassified/codex"
        assert unclassified_identity("kimi", "cli", None).project_id == \
            "unclassified/kimi"

    def test_degradation_is_visible(self, resolver):
        identity = resolve_identity("codex", {"sid": "s"}, resolver=resolver)
        session = apply_identity({"sid": "s"}, identity)
        assert session["identity_status"] == "unclassified"
        assert session["project_identity_diagnostics"][0]["status"] == "degraded"

    def test_the_two_fallback_reasons_stay_distinguishable(self):
        """"nothing to go on" and "evidence was rejected" need different fixes."""
        assert unclassified_identity("codex", "cli", None).resolution_method == \
            "insufficient_evidence"
        assert unclassified_identity(
            "codex", "cli", None, method="invalid_evidence_fallback"
        ).resolution_method == "invalid_evidence_fallback"


# ---------------------------------------------------------------------------
# Invalid is refused before writing
# ---------------------------------------------------------------------------
class TestInvalidIsRefused:
    def test_no_provider_is_refused(self, resolver):
        with pytest.raises(IdentityRefused):
            resolve_identity("", {"sid": "s"}, resolver=resolver)

    @pytest.mark.parametrize("envelope", [
        "not an object", 42, [], {"project_id": "x"},
        {"project_id": "", "project_name": "n", "resolution_method": "m"},
        {"project_name": "n", "resolution_method": "m"},
    ])
    def test_a_malformed_envelope_is_refused(self, envelope):
        with pytest.raises(IdentityRefused):
            validate_envelope(envelope, provider="codex")

    def test_a_well_formed_envelope_passes(self):
        envelope = {"project_id": "acme", "project_name": "Acme",
                    "resolution_method": "git_root"}
        assert validate_envelope(envelope, provider="codex") == envelope

    def test_an_envelope_contradicting_its_evidence_is_refused(
            self, resolver, repo_with_worktree):
        repo, _ = repo_with_worktree
        session = {
            "sid": "s", "cwd": str(repo),
            "project_identity": {"project_id": "some-other-project",
                                 "project_name": "Other",
                                 "resolution_method": "git_root"},
        }
        with pytest.raises(IdentityRefused) as caught:
            resolve_identity("codex", session, resolver=resolver)
        assert "contradicts" in str(caught.value)

    def test_an_envelope_that_gave_up_may_be_superseded(self, resolver,
                                                       repo_with_worktree):
        """A hook that could not resolve must not block a better answer.

        The hook fires before the file exists on disk; the tailer reads it
        later, with more context. Treating the earlier guess as binding would
        keep sessions unclassified for no reason.
        """
        repo, _ = repo_with_worktree
        session = {
            "sid": "s", "cwd": str(repo),
            "project_identity": {"project_id": "unclassified/codex",
                                 "project_name": "Unclassified (codex)",
                                 "resolution_method": "insufficient_evidence"},
        }
        identity = resolve_identity("codex", session, resolver=resolver)
        assert identity.status is IdentityStatus.CLASSIFIED

    def test_refusal_happens_before_any_write(self, resolver, tmp_path):
        """Nothing is emitted for a refused session — no partial state."""
        from hive_mind.capture import engine
        from hive_mind.capture.ingest import ingest

        emitted = []
        original = engine.emit
        engine.emit = lambda *a, **k: emitted.append(a) or 1
        try:
            store = engine.SeenStore(tmp_path / "seen.db")
            refused = []
            result = ingest("", {"sid": "s"}, store,
                            resolver=resolver, on_refused=refused.append)
            store.close()
        finally:
            engine.emit = original
        assert result == 0
        assert emitted == []
        assert refused and isinstance(refused[0], IdentityRefused)


# ---------------------------------------------------------------------------
# Exactly one implementation
# ---------------------------------------------------------------------------
class TestOneImplementation:
    def test_the_legacy_module_is_a_shim(self):
        source = (CAPTURE / "capture_core.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        defined = [n.name for n in tree.body
                   if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
        assert defined == [], f"capture_core still implements {defined}"

    def test_the_shim_re_exports_the_enforcing_ingest(self):
        sys.path.insert(0, str(ROOT))
        try:
            import scripts.capture.capture_core as shim
        finally:
            sys.path.pop(0)
        from hive_mind.capture.ingest import ingest

        assert shim.ingest is ingest

    def test_no_second_engine_lives_under_scripts(self):
        """A copy reappearing under scripts/ is the failure mode to catch."""
        offenders = []
        for path in CAPTURE.rglob("*.py"):
            source = path.read_text(encoding="utf-8", errors="replace")
            if "def emit_prompt" in source or "def _emit_body" in source:
                offenders.append(path.relative_to(ROOT).as_posix())
        assert offenders == [], f"a second transport engine appeared: {offenders}"

    def test_the_transport_refuses_a_session_nobody_identified(self, tmp_path):
        from hive_mind.capture import engine

        store = engine.SeenStore(tmp_path / "seen.db")
        try:
            with pytest.raises(engine.CanonicalIdentityRequired):
                engine.emit("codex", {"sid": "s", "prompt": "hi"}, store)
        finally:
            store.close()

    @pytest.mark.parametrize("runner", ["capture-realtime.py", "capture-tailer.py"])
    def test_no_entrypoint_resolves_identity_itself(self, runner):
        text = (CAPTURE / runner).read_text(encoding="utf-8")
        code = "\n".join(line for line in text.splitlines()
                         if not line.lstrip().startswith("#"))
        assert "attach_project_identity" not in code, (
            f"{runner} resolves identity itself; ingest() already does"
        )
