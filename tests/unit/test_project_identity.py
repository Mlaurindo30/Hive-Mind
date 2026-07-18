from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
import yaml

from scripts.capture.project_identity import (
    DEFAULT_REGISTRY_PATH,
    ProjectAliasRegistry,
    ProjectIdentity,
    ProjectIdentityError,
    ProjectIdentityResolver,
    RegistryValidationError,
    canonical_path_key,
    normalize_git_remote,
)


FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "project-aliases.yaml"


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.stdout.strip()


def _repo(path: Path, *, remote: str | None = None) -> Path:
    path.mkdir(parents=True)
    _git(path, "init")
    _git(path, "config", "user.email", "identity-tests@example.invalid")
    _git(path, "config", "user.name", "Identity Tests")
    (path / "README.md").write_text("identity\n", encoding="utf-8")
    _git(path, "add", "README.md")
    _git(path, "commit", "-m", "initial")
    if remote:
        _git(path, "remote", "add", "origin", remote)
    return path


def _registry(tmp_path: Path, *projects: dict) -> Path:
    path = tmp_path / "aliases.yaml"
    path.write_text(
        yaml.safe_dump(
            {"schema_version": 1, "projects": list(projects)},
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def _entry(project_id: str = "alpha", project_name: str = "Alpha", **extra) -> dict:
    return {"project_id": project_id, "project_name": project_name, **extra}


def test_project_identity_is_immutable_versioned_and_serializable():
    identity = ProjectIdentity(
        project_id="alpha",
        project_name="Alpha",
        workspace_root="C:\\Work\\Alpha",
        repository_root=None,
        repository_remote=None,
        git_common_dir=None,
        worktree_name=None,
        branch=None,
        provider="copilot",
        surface="ide",
        resolution_method="explicit",
        resolution_confidence=1.0,
        referenced_projects=("beta",),
    )

    assert identity.schema_version == 1
    assert identity.to_dict()["referenced_projects"] == ["beta"]
    assert json.loads(identity.to_json())["project_id"] == "alpha"
    with pytest.raises(FrozenInstanceError):
        identity.project_id = "changed"


def test_explicit_id_has_highest_precedence(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    registry = _registry(tmp_path, _entry(roots=[str(workspace)]))
    resolver = ProjectIdentityResolver(registry_path=registry)

    identity = resolver.resolve(
        provider="copilot",
        surface="ide",
        cwd=workspace,
        explicit_project_id="chosen/project",
        explicit_project_name="Chosen Project",
        env={"HIVE_PROJECT_ID": "environment"},
        official_workspace=workspace,
    )

    assert identity.project_id == "chosen/project"
    assert identity.project_name == "Chosen Project"
    assert identity.resolution_method == "explicit"
    assert identity.resolution_confidence == 1.0


@pytest.mark.parametrize("unsafe", ["", "../escape", "Has Spaces", "/leading", "trailing/", "a//b"])
def test_explicit_id_rejects_unsafe_values(unsafe):
    with pytest.raises(ProjectIdentityError):
        ProjectIdentityResolver(registry=ProjectAliasRegistry.empty()).resolve(
            provider="codex", surface="cli", explicit_project_id=unsafe
        )


def test_environment_id_precedes_environment_root_and_workspace(tmp_path):
    env_root = tmp_path / "env-root"
    official = tmp_path / "official"
    env_root.mkdir()
    official.mkdir()
    registry = _registry(
        tmp_path,
        _entry("env-root", "Environment Root", roots=[str(env_root)]),
        _entry("official", "Official", roots=[str(official)]),
    )
    identity = ProjectIdentityResolver(registry_path=registry).resolve(
        provider="qwen",
        surface="desktop",
        cwd=official,
        official_workspace=official,
        env={"HIVE_PROJECT_ID": "environment-id", "HIVE_PROJECT_ROOT": str(env_root)},
    )

    assert identity.project_id == "environment-id"
    assert identity.resolution_method == "environment_id"


def test_environment_root_precedes_official_workspace(tmp_path):
    env_root = tmp_path / "env-root"
    official = tmp_path / "official"
    env_root.mkdir()
    official.mkdir()
    registry = _registry(
        tmp_path,
        _entry("env-project", "Environment Project", roots=[str(env_root)]),
        _entry("official-project", "Official Project", roots=[str(official)]),
    )
    identity = ProjectIdentityResolver(registry_path=registry).resolve(
        provider="qwen",
        surface="desktop",
        cwd=official,
        official_workspace=official,
        env={"HIVE_PROJECT_ROOT": str(env_root)},
    )

    assert identity.project_id == "env-project"
    assert identity.workspace_root == str(env_root.resolve())
    assert identity.resolution_method == "environment_root"


def test_official_workspace_precedes_cwd(tmp_path):
    official = tmp_path / "official"
    cwd = tmp_path / "cwd"
    official.mkdir()
    cwd.mkdir()
    registry = _registry(
        tmp_path,
        _entry("official", "Official", roots=[str(official)]),
        _entry("cwd", "Current", roots=[str(cwd)]),
    )
    identity = ProjectIdentityResolver(registry_path=registry).resolve(
        provider="antigravity",
        surface="ide",
        cwd=cwd,
        official_workspace=official,
        env={},
    )

    assert identity.project_id == "official"
    assert identity.workspace_root == str(official.resolve())
    assert identity.resolution_method == "official_workspace"


def test_real_git_root_and_normalized_remote_resolve_registry(tmp_path):
    repo = _repo(tmp_path / "Alpha Repo", remote="git@github.com:Example/Alpha.git")
    registry = _registry(
        tmp_path,
        _entry(
            remotes=["https://github.com/example/alpha.git"],
            roots=[str(repo)],
        ),
    )
    subdir = repo / "subdir"
    subdir.mkdir()
    identity = ProjectIdentityResolver(registry_path=registry).resolve(
        provider="kimi", surface="cli", cwd=subdir, env={}
    )

    assert identity.project_id == "alpha"
    assert identity.repository_root == str(repo.resolve())
    assert identity.repository_remote == "github.com/example/alpha"
    assert identity.git_common_dir == str((repo / ".git").resolve())
    assert identity.branch
    assert identity.resolution_method == "git_root"


def test_real_worktree_shares_local_identity_and_preserves_metadata(tmp_path):
    repo = _repo(tmp_path / "main")
    worktree = tmp_path / "feature checkout"
    _git(repo, "worktree", "add", "-b", "feature/identity", str(worktree))

    resolver = ProjectIdentityResolver(registry=ProjectAliasRegistry.empty())
    main_identity = resolver.resolve(provider="codex", surface="cli", cwd=repo, env={})
    worktree_identity = resolver.resolve(provider="codex", surface="cli", cwd=worktree, env={})

    assert main_identity.project_id == worktree_identity.project_id
    assert main_identity.git_common_dir == worktree_identity.git_common_dir
    assert worktree_identity.repository_root == str(worktree.resolve())
    assert worktree_identity.worktree_name == worktree.name
    assert worktree_identity.branch == "feature/identity"


def test_git_repository_without_remote_uses_deterministic_common_dir_id(tmp_path):
    repo = _repo(tmp_path / "local only")
    resolver = ProjectIdentityResolver(registry=ProjectAliasRegistry.empty())

    first = resolver.resolve(provider="hermes", surface="desktop", cwd=repo, env={})
    second = resolver.resolve(provider="hermes", surface="desktop", cwd=repo, env={})

    assert first.project_id == second.project_id
    assert first.project_id.startswith("local/")
    assert first.repository_remote is None
    assert first.resolution_method == "git_common_dir"


def test_detached_head_has_no_branch_and_keeps_identity(tmp_path):
    repo = _repo(tmp_path / "detached")
    resolver = ProjectIdentityResolver(registry=ProjectAliasRegistry.empty())
    attached = resolver.resolve(provider="codex", surface="cli", cwd=repo, env={})
    _git(repo, "checkout", "--detach", "HEAD")
    detached = resolver.resolve(provider="codex", surface="cli", cwd=repo, env={})

    assert detached.project_id == attached.project_id
    assert detached.branch is None


def test_unknown_https_and_ssh_remotes_have_same_deterministic_id(tmp_path):
    first_repo = _repo(tmp_path / "one", remote="https://token@example.com/Owner/Repo.git?x=1")
    second_repo = _repo(tmp_path / "two", remote="git@example.com:Owner/Repo.git")
    resolver = ProjectIdentityResolver(registry=ProjectAliasRegistry.empty())

    first = resolver.resolve(provider="qwen", surface="cli", cwd=first_repo, env={})
    second = resolver.resolve(provider="qwen", surface="cli", cwd=second_repo, env={})

    assert first.repository_remote == "example.com/owner/repo"
    assert second.repository_remote == first.repository_remote
    assert second.project_id == first.project_id
    assert first.project_id.startswith("git/")
    assert "token" not in first.project_id
    assert "@" not in first.project_id
    assert "token" not in first.repository_remote
    assert "@" not in first.repository_remote


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://user:secret@GitHub.com/Owner/Repo.git", "github.com/owner/repo"),
        ("ssh://git@github.com/Owner/Repo.git", "github.com/owner/repo"),
        ("git@github.com:Owner/Repo.git", "github.com/owner/repo"),
    ],
)
def test_remote_normalization_removes_credentials_and_syntax(raw, expected):
    assert normalize_git_remote(raw) == expected


def test_malformed_remote_port_is_safe_and_deterministic(tmp_path):
    remote = "https://user:secret@github.com:invalid/Owner/Repo.git"
    repo = _repo(tmp_path / "malformed remote", remote=remote)
    resolver = ProjectIdentityResolver(registry=ProjectAliasRegistry.empty())

    first = resolver.resolve(provider="qwen", surface="cli", cwd=repo, env={})
    second = resolver.resolve(provider="qwen", surface="cli", cwd=repo, env={})

    assert normalize_git_remote(remote) == "github.com/owner/repo"
    assert first.repository_remote == "github.com/owner/repo"
    assert first.project_id == second.project_id
    assert first.project_id.startswith("git/repo-")
    assert "user" not in first.repository_remote
    assert "secret" not in first.repository_remote


def test_non_git_directory_with_conflicting_markers_is_unclassified(tmp_path):
    workspace = tmp_path / "ambiguous markers"
    workspace.mkdir()
    (workspace / ".alpha-project").write_text("alpha", encoding="utf-8")
    (workspace / ".beta-project").write_text("beta", encoding="utf-8")
    registry = _registry(
        tmp_path,
        _entry("alpha", "Alpha", markers=[{"all": [".alpha-project"]}]),
        _entry("beta", "Beta", markers=[{"all": [".beta-project"]}]),
    )

    identity = ProjectIdentityResolver(registry_path=registry).resolve(
        provider="mimo", surface="ide", cwd=workspace, env={}
    )

    assert identity.project_id == "unclassified/mimo"
    assert identity.resolution_method == "unclassified_provider"


def test_non_git_directory_does_not_use_basename(tmp_path):
    directory = tmp_path / "ImportantProject"
    directory.mkdir()

    identity = ProjectIdentityResolver(registry=ProjectAliasRegistry.empty()).resolve(
        provider="mimo", surface="ide", cwd=directory, env={}
    )

    assert identity.project_id == "unclassified/mimo"
    assert identity.project_name == "Unclassified (mimo)"
    assert identity.resolution_method == "unclassified_provider"


def test_unicode_spaces_and_marker_fallback(tmp_path):
    workspace = tmp_path / "Área de Trabalho" / "Projeto São Paulo"
    workspace.mkdir(parents=True)
    (workspace / ".projeto-identidade").write_text("ok", encoding="utf-8")
    registry = _registry(
        tmp_path,
        _entry(
            "sao-paulo",
            "Projeto São Paulo",
            markers=[{"all": [".projeto-identidade"]}],
        ),
    )

    identity = ProjectIdentityResolver(registry_path=registry).resolve(
        provider="copilot", surface="ide", cwd=workspace, env={}
    )

    assert identity.project_id == "sao-paulo"
    assert identity.workspace_root == str(workspace.resolve())
    assert identity.resolution_method == "marker"


def test_explicit_alias_maps_to_canonical_project(tmp_path):
    registry = _registry(
        tmp_path,
        _entry(aliases=["Alpha Legacy", "alpha-worktree"]),
    )
    identity = ProjectIdentityResolver(registry_path=registry).resolve(
        provider="hermes",
        surface="desktop",
        explicit_project="ALPHA LEGACY",
        env={},
    )

    assert identity.project_id == "alpha"
    assert identity.project_name == "Alpha"
    assert identity.resolution_method == "explicit_alias"


def test_windows_path_keys_fold_case_and_separators():
    assert canonical_path_key("C:\\Users\\Name\\Alpha\\") == canonical_path_key(
        r"c:/users/name/alpha"
    )


def test_unc_path_keys_fold_case_without_losing_unc_identity():
    key = canonical_path_key(r"\\SERVER\Share\Folder\\")
    assert key == canonical_path_key(r"//server/share/folder")
    assert key.startswith("//server/share")


@pytest.mark.skipif(os.name != "nt", reason="junction behavior is Windows-specific")
def test_junction_and_target_have_same_canonical_key(tmp_path):
    target = tmp_path / "real target"
    link = tmp_path / "junction"
    target.mkdir()
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert canonical_path_key(link) == canonical_path_key(target)


def test_generic_conversation_never_activates_mentioned_project(tmp_path):
    registry = ProjectAliasRegistry.load(FIXTURE)
    resolver = ProjectIdentityResolver(registry=registry)

    identity = resolver.resolve(
        provider="copilot",
        surface="ide",
        env={},
        conversation_text="Please compare Alpha with Beta",
        referenced_projects=["Alpha Legacy", "beta", "Unknown Mention"],
    )

    assert identity.project_id == "unclassified/copilot"
    assert identity.referenced_projects == ("alpha", "beta", "Unknown Mention")


def test_references_do_not_collapse_or_replace_primary_project(tmp_path):
    workspace = tmp_path / "alpha"
    workspace.mkdir()
    registry = _registry(
        tmp_path,
        _entry("alpha", "Alpha", roots=[str(workspace)]),
        _entry("beta", "Beta", aliases=["Beta Legacy"]),
    )
    identity = ProjectIdentityResolver(registry_path=registry).resolve(
        provider="copilot",
        surface="ide",
        cwd=workspace,
        env={},
        referenced_projects=["Beta Legacy", "alpha", "Beta Legacy"],
    )

    assert identity.project_id == "alpha"
    assert identity.referenced_projects == ("beta", "alpha")


def test_registry_fixture_loads_and_matches_remote_and_alias():
    registry = ProjectAliasRegistry.load(FIXTURE)

    assert registry.by_remote("git@github.com:Example/Alpha.git").project_id == "alpha"
    assert registry.by_alias("ALPHA LEGACY").project_id == "alpha"


@pytest.mark.parametrize(
    "payload",
    [
        "not: [valid",
        "[]",
        "schema_version: 99\nprojects: []\n",
        "schema_version: 1\nprojects: [{project_name: Missing Id}]\n",
        "schema_version: 1\nprojects: [{project_id: '../bad', project_name: Bad}]\n",
        (
            "schema_version: 1\nprojects:\n"
            "  - {project_id: one, project_name: One, aliases: [shared]}\n"
            "  - {project_id: two, project_name: Two, aliases: [SHARED]}\n"
        ),
        (
            "schema_version: 1\nprojects:\n"
            "  - {project_id: one, project_name: One, remotes: [git@example.com:a/r.git]}\n"
            "  - {project_id: two, project_name: Two, remotes: [https://example.com/a/r.git]}\n"
        ),
    ],
)
def test_malformed_or_ambiguous_registry_is_rejected(tmp_path, payload):
    path = tmp_path / "invalid.yaml"
    path.write_text(payload, encoding="utf-8")

    with pytest.raises(RegistryValidationError):
        ProjectAliasRegistry.load(path)

def test_shipped_registry_maps_all_required_hive_mind_evidence():
    registry = ProjectAliasRegistry.load(DEFAULT_REGISTRY_PATH)

    assert registry.by_root(r"D:\Hive-Mind").project_id == "hive-mind"
    assert registry.by_root(
        r"D:\Hive-Mind\backups\worktrees\hive-mind-windows-zero-install"
    ).project_id == "hive-mind"
    assert registry.by_remote(
        "git@github.com:Mlaurindo30/Hive-Mind.git"
    ).project_id == "hive-mind"
    assert registry.by_alias("Hive-Mind").project_id == "hive-mind"
    assert registry.by_alias(
        "hive-mind-windows-zero-install"
    ).project_id == "hive-mind"
    assert registry.by_alias(
        "Hive-Mind/hive-mind-windows-zero-install"
    ).project_id == "hive-mind"


def test_duplicate_root_evidence_across_projects_is_rejected(tmp_path):
    shared = tmp_path / "shared"
    shared.mkdir()
    path = _registry(
        tmp_path,
        _entry("one", "One", roots=[str(shared)]),
        _entry("two", "Two", roots=[str(shared).swapcase()]),
    )

    with pytest.raises(RegistryValidationError):
        ProjectAliasRegistry.load(path)


def test_unsafe_marker_traversal_is_rejected(tmp_path):
    path = _registry(
        tmp_path,
        _entry("one", "One", markers=[{"all": ["../secret"]}]),
    )

    with pytest.raises(RegistryValidationError):
        ProjectAliasRegistry.load(path)


def test_official_non_git_workspaces_use_full_path_identity_without_collisions(tmp_path):
    first = tmp_path / "customer-a" / "Cliente"
    second = tmp_path / "customer-b" / "Cliente"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    resolver = ProjectIdentityResolver(registry=ProjectAliasRegistry.empty())

    first_identity = resolver.resolve(
        provider="codex", surface="cli", cwd=first,
        official_workspace=first, env={},
    )
    second_identity = resolver.resolve(
        provider="codex", surface="cli", cwd=second,
        official_workspace=second, env={},
    )

    expected_digest = hashlib.sha256(
        canonical_path_key(first).encode("utf-8")
    ).hexdigest()[:12]
    assert first_identity.project_id == f"root/cliente-{expected_digest}"
    assert first_identity.project_name == "Cliente"
    assert first_identity.resolution_method == "official_workspace"
    assert first_identity.workspace_root == str(first.resolve())
    assert second_identity.project_id.startswith("root/cliente-")
    assert second_identity.project_id != first_identity.project_id
