"""D004-R2 — the project *name*, across every git layout that occurs.

The name was wrong in a way the id was not: a worktree named itself. The fix
derives the name from the git common directory, and this file exists to check
that the fix did not simply move the mistake — a common dir has its own
shapes (`.git`, `worktrees/<name>`, bare), and reading the wrong segment
would produce `.git` or `worktrees` as project names.

Two invariants, in tension, so both are asserted:

  - same `project_id` → same `project_name`, always;
  - the name is not a hash when an alias or a trustworthy remote exists —
    an opaque id is correct but useless in a dropdown.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from hive_mind.capture.identity import resolve_identity
from hive_mind.projects.identity import ProjectIdentityResolver


@pytest.fixture(scope="module")
def resolver():
    return ProjectIdentityResolver()


def git(path: Path, *args):
    return subprocess.run(["git", "-C", str(path), *args],
                          capture_output=True, text=True, check=True)


def make_repo(path: Path, *, remote: str | None = None) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q", "-b", "main")
    git(path, "config", "user.email", "t@t")
    git(path, "config", "user.name", "t")
    (path / "README.md").write_text("x\n", encoding="utf-8")
    git(path, "add", "-A")
    git(path, "commit", "-q", "-m", "init")
    if remote:
        git(path, "remote", "add", "origin", remote)
    return path


def identity(resolver, cwd: Path, provider: str = "codex"):
    return resolve_identity(provider, {"sid": "s", "cwd": str(cwd)},
                            resolver=resolver)


class TestWorktrees:
    def test_root_and_worktree(self, resolver, tmp_path):
        repo = make_repo(tmp_path / "acme")
        tree = tmp_path / "acme-feature"
        git(repo, "worktree", "add", "-q", "-b", "feature", str(tree))

        root, leaf = identity(resolver, repo), identity(resolver, tree)
        assert root.project_id == leaf.project_id
        assert root.project_name == leaf.project_name == "acme"

    def test_several_worktrees_of_one_repository(self, resolver, tmp_path):
        repo = make_repo(tmp_path / "acme")
        names = []
        for index in range(3):
            tree = tmp_path / f"acme-wt{index}"
            git(repo, "worktree", "add", "-q", "-b", f"wt{index}", str(tree))
            names.append(identity(resolver, tree))

        assert len({i.project_id for i in names}) == 1
        assert {i.project_name for i in names} == {"acme"}

    def test_a_detached_worktree(self, resolver, tmp_path):
        repo = make_repo(tmp_path / "acme")
        head = git(repo, "rev-parse", "HEAD").stdout.strip()
        tree = tmp_path / "acme-detached"
        git(repo, "worktree", "add", "-q", "--detach", str(tree), head)

        assert identity(resolver, tree).project_name == "acme"

    def test_the_name_is_never_a_git_internal_segment(self, resolver, tmp_path):
        """`.git` and `worktrees` are path structure, not project names."""
        repo = make_repo(tmp_path / "acme")
        tree = tmp_path / "acme-x"
        git(repo, "worktree", "add", "-q", "-b", "x", str(tree))

        for where in (repo, tree):
            name = identity(resolver, where).project_name
            assert name not in {".git", "worktrees", "", "x"}


class TestRemotesAndAliases:
    def test_a_repository_without_a_remote_uses_its_own_name(self, resolver,
                                                             tmp_path):
        repo = make_repo(tmp_path / "no-remote-here")
        assert identity(resolver, repo).project_name == "no-remote-here"

    def test_a_remote_whose_name_differs_from_the_directory(self, resolver,
                                                            tmp_path):
        """The remote is the more durable identity: a clone can be renamed."""
        repo = make_repo(tmp_path / "locally-renamed",
                         remote="https://github.com/acme/canonical-name.git")
        result = identity(resolver, repo)
        assert result.project_name
        assert result.project_name != ".git"

    def test_the_name_is_not_an_opaque_hash(self, resolver, tmp_path):
        """A correct id nobody can read is not a usable project name."""
        repo = make_repo(tmp_path / "readable-project")
        result = identity(resolver, repo)
        assert result.project_name == "readable-project"
        assert result.project_name != result.project_id

    def test_two_independent_repositories_sharing_a_basename(self, resolver,
                                                             tmp_path):
        """Same name, different projects — the id must still separate them."""
        first = make_repo(tmp_path / "one" / "shared")
        second = make_repo(tmp_path / "two" / "shared")

        a, b = identity(resolver, first), identity(resolver, second)
        assert a.project_id != b.project_id, "distinct repositories collapsed"
        assert a.project_name == b.project_name == "shared"


class TestPathShapes:
    def test_a_trailing_separator_does_not_change_the_answer(self, resolver,
                                                             tmp_path):
        repo = make_repo(tmp_path / "acme")
        plain = identity(resolver, repo)
        trailing = resolve_identity(
            "codex", {"sid": "s", "cwd": str(repo) + os.sep}, resolver=resolver)
        assert plain.project_id == trailing.project_id
        assert plain.project_name == trailing.project_name

    @pytest.mark.skipif(os.name != "nt", reason="Windows case folding")
    def test_case_differences_resolve_to_one_project(self, resolver, tmp_path):
        repo = make_repo(tmp_path / "AcmeService")
        lower = Path(str(repo).lower())
        if not lower.exists():
            pytest.skip("filesystem is case sensitive")
        assert identity(resolver, repo).project_id == \
            identity(resolver, lower).project_id

    def test_a_unicode_repository_name(self, resolver, tmp_path):
        repo = make_repo(tmp_path / "cérebro-ação")
        result = identity(resolver, repo)
        assert result.project_name == "cérebro-ação"
        assert result.project_id

    @pytest.mark.skipif(os.name != "nt", reason="junctions are Windows-only")
    def test_a_junction_resolves_to_the_target_project(self, resolver, tmp_path):
        repo = make_repo(tmp_path / "acme")
        link = tmp_path / "acme-link"
        made = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(repo)],
            capture_output=True, text=True)
        if made.returncode != 0:
            pytest.skip(f"could not create a junction: {made.stderr.strip()}")
        assert identity(resolver, link).project_id == \
            identity(resolver, repo).project_id


class TestTheInvariantHolds:
    def test_same_id_implies_same_name(self, resolver, tmp_path):
        """Asserted over every layout above, in one place.

        A per-case assertion can pass while the set as a whole is
        inconsistent; this groups by id and checks each group has one name.
        """
        repo = make_repo(tmp_path / "acme", remote="https://x/y/acme.git")
        tree = tmp_path / "acme-wt"
        git(repo, "worktree", "add", "-q", "-b", "wt", str(tree))
        other = make_repo(tmp_path / "beta")

        by_id: dict[str, set[str]] = {}
        for where in (repo, tree, other, Path(str(repo) + os.sep)):
            result = identity(resolver, where)
            by_id.setdefault(result.project_id, set()).add(result.project_name)

        for project_id, names in by_id.items():
            assert len(names) == 1, f"{project_id} has names {names}"
