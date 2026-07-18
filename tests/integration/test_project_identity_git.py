from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.capture.project_identity import (
    ProjectAliasRegistry,
    ProjectIdentityResolver,
)


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    return result.stdout.strip()


def _repository(path: Path, *, remote: str | None = None) -> Path:
    path.mkdir(parents=True)
    _git(path, "init", "--initial-branch=main")
    _git(path, "config", "user.email", "project-identity@example.invalid")
    _git(path, "config", "user.name", "Project Identity Integration")
    (path / "identity.txt").write_text("canonical identity\n", encoding="utf-8")
    _git(path, "add", "identity.txt")
    _git(path, "commit", "-m", "initial identity fixture")
    if remote is not None:
        _git(path, "remote", "add", "origin", remote)
    return path


def _resolver() -> ProjectIdentityResolver:
    return ProjectIdentityResolver(registry=ProjectAliasRegistry.empty())


def test_root_and_linked_worktree_share_identity_but_keep_checkout_metadata(tmp_path):
    repository = _repository(tmp_path / "canonical repository")
    linked = tmp_path / "linked feature checkout"
    _git(
        repository,
        "worktree",
        "add",
        "-b",
        "feature/project-identity",
        str(linked),
    )

    root_identity = _resolver().resolve(
        provider="codex", surface="cli", cwd=repository, env={}
    )
    linked_identity = _resolver().resolve(
        provider="codex", surface="cli", cwd=linked, env={}
    )

    assert root_identity.project_id == linked_identity.project_id
    assert root_identity.git_common_dir == linked_identity.git_common_dir
    assert root_identity.repository_root == str(repository.resolve())
    assert linked_identity.repository_root == str(linked.resolve())
    assert root_identity.branch == "main"
    assert linked_identity.branch == "feature/project-identity"
    assert root_identity.worktree_name == repository.name
    assert linked_identity.worktree_name == linked.name
    assert root_identity.worktree_name != linked_identity.worktree_name


def test_detached_head_keeps_repository_identity_and_checkout_name(tmp_path):
    repository = _repository(tmp_path / "detached repository")
    resolver = _resolver()
    attached = resolver.resolve(
        provider="hermes", surface="desktop", cwd=repository, env={}
    )

    _git(repository, "checkout", "--detach", "HEAD")
    detached = resolver.resolve(
        provider="hermes", surface="desktop", cwd=repository, env={}
    )

    assert detached.project_id == attached.project_id
    assert detached.git_common_dir == attached.git_common_dir
    assert detached.branch is None
    assert detached.worktree_name == attached.worktree_name == repository.name


def test_unrelated_repositories_with_same_basename_do_not_collide(tmp_path):
    first = _repository(tmp_path / "first parent" / "shared-name")
    second = _repository(tmp_path / "second parent" / "shared-name")
    resolver = _resolver()

    first_identity = resolver.resolve(
        provider="qwen", surface="cli", cwd=first, env={}
    )
    second_identity = resolver.resolve(
        provider="qwen", surface="cli", cwd=second, env={}
    )

    assert first.name == second.name
    assert first_identity.project_id.startswith("local/")
    assert second_identity.project_id.startswith("local/")
    assert first_identity.project_id != second_identity.project_id
    assert first_identity.git_common_dir != second_identity.git_common_dir


@pytest.mark.parametrize(
    ("checkout", "remote"),
    [
        ("https", "https://user:secret@GitHub.com/Canonical/Identity.git"),
        ("ssh-url", "ssh://git@github.com/Canonical/Identity.git"),
        ("scp", "git@github.com:Canonical/Identity.git"),
    ],
)
def test_equivalent_real_git_remotes_are_credential_free_and_stable(
    tmp_path, checkout, remote
):
    repository = _repository(tmp_path / checkout, remote=remote)

    identity = _resolver().resolve(
        provider="kimi", surface="cli", cwd=repository, env={}
    )

    assert identity.repository_remote == "github.com/canonical/identity"
    assert identity.project_id.startswith("git/identity-")
    assert "user" not in identity.repository_remote
    assert "secret" not in identity.repository_remote
    assert "git@" not in identity.repository_remote


def test_equivalent_real_git_remotes_produce_one_project_id(tmp_path):
    remotes = (
        "https://user:secret@GitHub.com/Canonical/Identity.git",
        "ssh://git@github.com/Canonical/Identity.git",
        "git@github.com:Canonical/Identity.git",
    )
    identities = [
        _resolver().resolve(
            provider="kimi",
            surface="cli",
            cwd=_repository(tmp_path / f"checkout-{index}", remote=remote),
            env={},
        )
        for index, remote in enumerate(remotes)
    ]

    assert {identity.repository_remote for identity in identities} == {
        "github.com/canonical/identity"
    }
    assert len({identity.project_id for identity in identities}) == 1


def test_repository_without_remote_has_stable_local_identity_from_nested_cwd(tmp_path):
    repository = _repository(tmp_path / "local repository")
    nested = repository / "src" / "package"
    nested.mkdir(parents=True)
    resolver = _resolver()

    from_root = resolver.resolve(
        provider="mimo", surface="ide", cwd=repository, env={}
    )
    from_nested = resolver.resolve(
        provider="mimo", surface="ide", cwd=nested, env={}
    )

    assert from_root.repository_remote is None
    assert from_root.resolution_method == "git_common_dir"
    assert from_root.project_id.startswith("local/")
    assert from_nested.project_id == from_root.project_id
    assert from_nested.git_common_dir == from_root.git_common_dir