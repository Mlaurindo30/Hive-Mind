"""Canonical project identity resolution for universal capture.

This module classifies the project a provider operated in. It deliberately does
not resolve the Hive-Mind installation root in src/hive_mind/project.py.
"""
from __future__ import annotations

import hashlib
import json
import ntpath
import os
import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import unquote, urlsplit

import yaml

SCHEMA_VERSION = 1
def _default_registry_path() -> Path:
    """Locate `config/project-aliases.yaml` without assuming this file's depth.

    The module used to derive it from `parents[2]`, which silently depended on
    living in `scripts/capture/`. Resolve the project root properly, and fall
    back to walking upwards so an unusual layout degrades to a clear
    file-not-found instead of a wrong path.
    """
    try:
        from hive_mind.project import resolve_project_root

        return resolve_project_root() / "config" / "project-aliases.yaml"
    except Exception:  # noqa: BLE001 - resolution must never break an import
        for parent in Path(__file__).resolve().parents:
            candidate = parent / "config" / "project-aliases.yaml"
            if candidate.is_file():
                return candidate
        return Path("config") / "project-aliases.yaml"


DEFAULT_REGISTRY_PATH = _default_registry_path()
_PROJECT_ID_RE = re.compile(
    r"^[a-z0-9][a-z0-9._-]*(?:/[a-z0-9][a-z0-9._-]*)*$"
)
_WINDOWS_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]")
_SCP_REMOTE_RE = re.compile(r"^(?:[^@/\\\s]+@)?([^:/\\\s]+):(.+)$")


class ProjectIdentityError(ValueError):
    """Raised when project identity evidence is invalid."""


class RegistryValidationError(ProjectIdentityError):
    """Raised when the declarative alias registry is malformed or ambiguous."""


def validate_project_id(value: str) -> str:
    """Validate and return a canonical storage-safe project ID."""
    if not isinstance(value, str):
        raise ProjectIdentityError("project_id must be a string")
    value = value.strip()
    if not value or not _PROJECT_ID_RE.fullmatch(value) or ".." in value.split("/"):
        raise ProjectIdentityError(f"unsafe project_id: {value!r}")
    return value


def _looks_windows_path(value: str) -> bool:
    return bool(
        _WINDOWS_PATH_RE.match(value)
        or value.startswith(("\\", "//"))
        or "\\" in value
    )


def _path_display(value: str | os.PathLike[str]) -> str:
    """Return a resolved display path without deliberately folding its case."""
    raw = os.path.expandvars(os.path.expanduser(os.fspath(value))).strip()
    if not raw:
        raise ProjectIdentityError("project path must not be empty")
    path = Path(raw)
    try:
        if path.exists():
            return str(path.resolve(strict=False))
    except OSError:
        pass
    if _looks_windows_path(raw):
        return ntpath.normpath(raw.replace("/", "\\"))
    return str(path.resolve(strict=False))


def canonical_path_key(value: str | os.PathLike[str]) -> str:
    """Return a comparison-only path key, resolving existing links."""
    display = _path_display(value)
    if _looks_windows_path(display):
        normalized = ntpath.normpath(display).replace("\\", "/")
        if normalized.startswith("//"):
            normalized = "//" + normalized.lstrip("/")
        return normalized.rstrip("/").casefold()
    normalized = os.path.normpath(display).replace("\\", "/")
    if os.name == "nt":
        normalized = normalized.casefold()
    return normalized.rstrip("/") or "/"


def normalize_git_remote(remote: str | None) -> str | None:
    """Normalize Git URLs to a credential-free host/path identity."""
    if remote is None:
        return None
    raw = remote.strip()
    if not raw:
        return None

    parsed = urlsplit(raw)
    if parsed.scheme and parsed.hostname:
        host = parsed.hostname.casefold()
        try:
            port = parsed.port
        except ValueError:
            port = None
        if port is not None:
            default_port = (
                parsed.scheme.casefold() == "https" and port == 443
            ) or (parsed.scheme.casefold() == "ssh" and port == 22)
            if not default_port:
                host = f"{host}:{port}"
        path = parsed.path
    else:
        match = _SCP_REMOTE_RE.match(raw)
        if not match or _WINDOWS_PATH_RE.match(raw):
            return None
        host, path = match.groups()
        host = host.casefold()

    path = unquote(path).replace("\\", "/").strip("/")
    if path.casefold().endswith(".git"):
        path = path[:-4]
    path = re.sub(r"/+", "/", path).strip("/").casefold()
    if not host or not path:
        return None
    return f"{host}/{path}"

@dataclass(frozen=True, slots=True)
class ProjectIdentity:
    """Immutable identity envelope attached to every normalized session."""

    project_id: str
    project_name: str
    workspace_root: str | None
    repository_root: str | None
    repository_remote: str | None
    git_common_dir: str | None
    worktree_name: str | None
    branch: str | None
    provider: str
    surface: str
    resolution_method: str
    resolution_confidence: float
    referenced_projects: tuple[str, ...] = field(default_factory=tuple)
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        validate_project_id(self.project_id)
        if self.schema_version != SCHEMA_VERSION:
            raise ProjectIdentityError(
                f"unsupported identity schema version: {self.schema_version}"
            )
        if not isinstance(self.project_name, str) or not self.project_name.strip():
            raise ProjectIdentityError("project_name must not be empty")
        if not 0.0 <= float(self.resolution_confidence) <= 1.0:
            raise ProjectIdentityError("resolution_confidence must be between 0 and 1")
        object.__setattr__(self, "referenced_projects", tuple(self.referenced_projects))

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["referenced_projects"] = list(self.referenced_projects)
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProjectIdentity":
        values = dict(payload)
        values["referenced_projects"] = tuple(values.get("referenced_projects") or ())
        return cls(**values)


@dataclass(frozen=True, slots=True)
class ProjectAlias:
    project_id: str
    project_name: str
    remotes: tuple[str, ...] = ()
    roots: tuple[str, ...] = ()
    git_common_dirs: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    marker_sets: tuple[tuple[str, ...], ...] = ()


class ProjectAliasRegistry:
    """Validated mapping from evidence to canonical projects."""

    def __init__(self, entries: Iterable[ProjectAlias] = ()) -> None:
        self.entries = tuple(entries)
        self._ids: dict[str, ProjectAlias] = {}
        self._aliases: dict[str, ProjectAlias] = {}
        self._remotes: dict[str, ProjectAlias] = {}
        self._roots: dict[str, ProjectAlias] = {}
        self._common_dirs: dict[str, ProjectAlias] = {}
        self._markers: dict[tuple[str, ...], ProjectAlias] = {}
        for entry in self.entries:
            project_id = validate_project_id(entry.project_id)
            if not entry.project_name.strip():
                raise RegistryValidationError(f"empty project_name for {entry.project_id!r}")
            self._claim(self._ids, project_id, entry, "project_id")
            for alias in (project_id, entry.project_name, *entry.aliases):
                key = alias.strip().casefold()
                if not key:
                    raise RegistryValidationError(f"empty alias for {entry.project_id!r}")
                self._claim(self._aliases, key, entry, "alias")
            for remote in entry.remotes:
                key = normalize_git_remote(remote)
                if not key:
                    raise RegistryValidationError(
                        f"invalid remote {remote!r} for {entry.project_id!r}"
                    )
                self._claim(self._remotes, key, entry, "remote")
            for root in entry.roots:
                self._claim(self._roots, canonical_path_key(root), entry, "canonical root")
            for common_dir in entry.git_common_dirs:
                self._claim(
                    self._common_dirs,
                    canonical_path_key(common_dir),
                    entry,
                    "git common directory",
                )
            for marker_set in entry.marker_sets:
                key = tuple(path.casefold() for path in marker_set)
                self._claim(self._markers, key, entry, "marker set")

    @staticmethod
    def _claim(index: dict[Any, ProjectAlias], key: Any, entry: ProjectAlias, evidence: str) -> None:
        existing = index.get(key)
        if existing is not None and existing.project_id != entry.project_id:
            raise RegistryValidationError(
                f"ambiguous {evidence} {key!r}: "
                f"{existing.project_id!r} and {entry.project_id!r}"
            )
        index[key] = entry

    @classmethod
    def empty(cls) -> "ProjectAliasRegistry":
        return cls(())

    @classmethod
    def load(cls, path: str | os.PathLike[str]) -> "ProjectAliasRegistry":
        config_path = Path(path)
        try:
            payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise RegistryValidationError(
                f"cannot load project alias registry {config_path}: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise RegistryValidationError("registry root must be a mapping")
        if payload.get("schema_version") != SCHEMA_VERSION:
            raise RegistryValidationError(
                f"unsupported registry schema_version: {payload.get('schema_version')!r}"
            )
        projects = payload.get("projects")
        if not isinstance(projects, list):
            raise RegistryValidationError("registry projects must be a list")
        entries: list[ProjectAlias] = []
        for position, raw in enumerate(projects):
            if not isinstance(raw, dict):
                raise RegistryValidationError(f"project entry {position} must be a mapping")
            try:
                project_id = validate_project_id(raw["project_id"])
                project_name = raw["project_name"]
            except KeyError as exc:
                raise RegistryValidationError(
                    f"project entry {position} is missing {exc.args[0]}"
                ) from exc
            except ProjectIdentityError as exc:
                raise RegistryValidationError(str(exc)) from exc
            if not isinstance(project_name, str) or not project_name.strip():
                raise RegistryValidationError(
                    f"project entry {position} has invalid project_name"
                )
            entries.append(
                ProjectAlias(
                    project_id=project_id,
                    project_name=project_name.strip(),
                    remotes=cls._strings(raw, "remotes", position),
                    roots=cls._strings(raw, "roots", position),
                    git_common_dirs=cls._strings(raw, "git_common_dirs", position),
                    aliases=cls._strings(raw, "aliases", position),
                    marker_sets=cls._parse_markers(raw.get("markers", []), position),
                )
            )
        try:
            return cls(entries)
        except ProjectIdentityError as exc:
            if isinstance(exc, RegistryValidationError):
                raise
            raise RegistryValidationError(str(exc)) from exc

    @staticmethod
    def _strings(raw: Mapping[str, Any], key: str, position: int) -> tuple[str, ...]:
        value = raw.get(key, [])
        if value is None:
            return ()
        if not isinstance(value, list) or not all(
            isinstance(item, str) and item.strip() for item in value
        ):
            raise RegistryValidationError(
                f"project entry {position} field {key} must be a list of strings"
            )
        return tuple(item.strip() for item in value)

    @staticmethod
    def _parse_markers(value: Any, position: int) -> tuple[tuple[str, ...], ...]:
        if value is None:
            return ()
        if not isinstance(value, list):
            raise RegistryValidationError(
                f"project entry {position} markers must be a list"
            )
        result: list[tuple[str, ...]] = []
        for marker in value:
            paths = [marker] if isinstance(marker, str) else (
                marker.get("all") if isinstance(marker, dict) else None
            )
            if not isinstance(paths, list) or not paths or not all(
                isinstance(path, str) and path.strip() for path in paths
            ):
                raise RegistryValidationError(
                    f"project entry {position} has invalid marker set"
                )
            normalized: list[str] = []
            for path in paths:
                clean = path.strip().replace("\\", "/")
                marker_path = Path(clean)
                if marker_path.is_absolute() or ".." in marker_path.parts:
                    raise RegistryValidationError(
                        f"unsafe marker path {path!r} in project entry {position}"
                    )
                normalized.append(clean)
            result.append(tuple(normalized))
        return tuple(result)

    def by_id(self, project_id: str) -> ProjectAlias | None:
        return self._ids.get(project_id)

    def by_alias(self, alias: str | None) -> ProjectAlias | None:
        return None if alias is None else self._aliases.get(alias.strip().casefold())

    def by_remote(self, remote: str | None) -> ProjectAlias | None:
        """Look up by Git remote, raw or already normalized.

        Callers are not consistent: the resolver passes `_inspect_git`'s output,
        which is already normalized ("github.com/owner/repo"), while config and
        tests pass raw URLs. A normalized remote has no scheme and no colon, so
        `normalize_git_remote` rejects it as neither URL nor SCP syntax and
        returns None — which silently made the registry's `remotes:` field dead
        for every real checkout. Index keys are always normalized at build time,
        so falling back to the trimmed input covers the already-normalized case.
        """
        if not remote:
            return None
        key = normalize_git_remote(remote) or remote.strip().casefold()
        return self._remotes.get(key)

    @staticmethod
    def _path_match(candidate: str | os.PathLike[str], index: Mapping[str, ProjectAlias]) -> ProjectAlias | None:
        key = canonical_path_key(candidate)
        matches = [
            (root, entry)
            for root, entry in index.items()
            if key == root or key.startswith(root.rstrip("/") + "/")
        ]
        return max(matches, key=lambda item: len(item[0]))[1] if matches else None

    def by_root(self, root: str | os.PathLike[str] | None) -> ProjectAlias | None:
        return None if root is None else self._path_match(root, self._roots)

    def by_common_dir(self, common_dir: str | os.PathLike[str] | None) -> ProjectAlias | None:
        return None if common_dir is None else self._path_match(common_dir, self._common_dirs)

    def marker_match(self, start: str | os.PathLike[str] | None) -> tuple[ProjectAlias, str] | None:
        if start is None or not self._markers:
            return None
        path = Path(_path_display(start))
        if path.is_file():
            path = path.parent
        for directory in (path, *path.parents):
            matches = {
                entry.project_id: entry
                for marker_set, entry in self._markers.items()
                if all((directory / marker).exists() for marker in marker_set)
            }
            if len(matches) > 1:
                return None
            if matches:
                entry = next(iter(matches.values()))
                return entry, str(directory.resolve(strict=False))
        return None


@dataclass(frozen=True, slots=True)
class _GitEvidence:
    repository_root: str
    git_common_dir: str
    repository_remote: str | None
    branch: str | None
    worktree_name: str | None

class ProjectIdentityResolver:
    """Resolve one canonical identity from provider, workspace and Git evidence."""

    def __init__(
        self,
        *,
        registry: ProjectAliasRegistry | None = None,
        registry_path: str | os.PathLike[str] | None = None,
        git_timeout: float = 3.0,
    ) -> None:
        if registry is not None and registry_path is not None:
            raise ProjectIdentityError("pass registry or registry_path, not both")
        if registry is not None:
            self.registry = registry
        else:
            path = Path(registry_path) if registry_path else DEFAULT_REGISTRY_PATH
            self.registry = (
                ProjectAliasRegistry.load(path)
                if path.is_file()
                else ProjectAliasRegistry.empty()
            )
        self.git_timeout = git_timeout

    def resolve(
        self,
        *,
        provider: str,
        surface: str,
        cwd: str | os.PathLike[str] | None = None,
        explicit_project_id: str | None = None,
        explicit_project_name: str | None = None,
        explicit_project: str | None = None,
        official_workspace: str | os.PathLike[str] | None = None,
        env: Mapping[str, str] | None = None,
        referenced_projects: Iterable[str] | None = None,
        conversation_text: str | None = None,
        semantic_activation: bool = False,
        semantic_score: float | None = None,
    ) -> ProjectIdentity:
        del conversation_text
        env_map = os.environ if env is None else env
        provider_key = _slug(provider) or "unknown"
        surface_key = _slug(surface) or "unknown"

        env_root = self._valid_directory(env_map.get("HIVE_PROJECT_ROOT"))
        official_root = self._valid_directory(official_workspace)
        cwd_root = self._valid_directory(cwd)
        workspace = env_root or official_root or cwd_root
        git = self._inspect_git(workspace)
        references = self._resolve_references(referenced_projects)

        if explicit_project_id is not None:
            project_id = validate_project_id(explicit_project_id)
            return self._identity(
                entry=self.registry.by_id(project_id),
                project_id=project_id,
                project_name=explicit_project_name,
                workspace=workspace,
                git=git,
                provider=provider_key,
                surface=surface_key,
                method="explicit",
                confidence=1.0,
                references=references,
            )

        if explicit_project is not None:
            entry = self.registry.by_alias(explicit_project)
            if entry is not None:
                return self._identity(
                    entry=entry,
                    workspace=workspace,
                    git=git,
                    provider=provider_key,
                    surface=surface_key,
                    method="explicit_alias",
                    confidence=1.0,
                    references=references,
                )
            project_id = validate_project_id(explicit_project)
            return self._identity(
                project_id=project_id,
                project_name=explicit_project_name,
                workspace=workspace,
                git=git,
                provider=provider_key,
                surface=surface_key,
                method="explicit",
                confidence=1.0,
                references=references,
            )

        env_id = env_map.get("HIVE_PROJECT_ID")
        if env_id is not None:
            project_id = validate_project_id(env_id)
            return self._identity(
                entry=self.registry.by_id(project_id),
                project_id=project_id,
                workspace=workspace,
                git=git,
                provider=provider_key,
                surface=surface_key,
                method="environment_id",
                confidence=0.99,
                references=references,
            )

        if env_root is not None:
            return self._resolve_root_source(
                env_root, git, provider_key, surface_key,
                "environment_root", 0.98, references,
            )

        if official_root is not None:
            return self._resolve_root_source(
                official_root, git, provider_key, surface_key,
                "official_workspace", 0.97, references,
            )

        if git is not None:
            root_entry = self.registry.by_root(git.repository_root)
            if root_entry is not None:
                return self._identity(
                    entry=root_entry, workspace=workspace, git=git,
                    provider=provider_key, surface=surface_key,
                    method="git_root", confidence=0.96, references=references,
                )
            common_entry = self.registry.by_common_dir(git.git_common_dir)
            if common_entry is not None:
                return self._identity(
                    entry=common_entry, workspace=workspace, git=git,
                    provider=provider_key, surface=surface_key,
                    method="git_common_dir", confidence=0.96, references=references,
                )
            remote_entry = self.registry.by_remote(git.repository_remote)
            if remote_entry is not None:
                return self._identity(
                    entry=remote_entry, workspace=workspace, git=git,
                    provider=provider_key, surface=surface_key,
                    method="git_remote", confidence=0.95, references=references,
                )
            if git.repository_remote:
                return self._identity(
                    project_id=_remote_project_id(git.repository_remote),
                    project_name=_remote_project_name(git.repository_remote),
                    workspace=workspace, git=git,
                    provider=provider_key, surface=surface_key,
                    method="git_remote", confidence=0.90, references=references,
                )
            return self._identity(
                project_id=_local_project_id(git.git_common_dir, git.repository_root),
                project_name=Path(git.repository_root).name,
                workspace=workspace, git=git,
                provider=provider_key, surface=surface_key,
                method="git_common_dir", confidence=0.88, references=references,
            )

        root_entry = self.registry.by_root(workspace)
        if root_entry is not None:
            return self._identity(
                entry=root_entry, workspace=workspace, git=None,
                provider=provider_key, surface=surface_key,
                method="alias_root", confidence=0.90, references=references,
            )

        marker = self.registry.marker_match(workspace)
        if marker is not None:
            entry, marker_root = marker
            return self._identity(
                entry=entry, workspace=marker_root, git=None,
                provider=provider_key, surface=surface_key,
                method="marker", confidence=0.80, references=references,
            )

        if (
            semantic_activation
            and semantic_score is not None
            and semantic_score >= 0.90
            and len(references) == 1
        ):
            entry = self.registry.by_alias(references[0])
            if entry is not None:
                return self._identity(
                    entry=entry, workspace=workspace, git=None,
                    provider=provider_key, surface=surface_key,
                    method="semantic_reference", confidence=float(semantic_score),
                    references=references,
                )

        return self._identity(
            project_id=f"unclassified/{provider_key}",
            project_name=f"Unclassified ({provider_key})",
            workspace=workspace, git=None,
            provider=provider_key, surface=surface_key,
            method="unclassified_provider", confidence=0.0, references=references,
        )

    def _resolve_root_source(
        self,
        root: str,
        git: _GitEvidence | None,
        provider: str,
        surface: str,
        method: str,
        confidence: float,
        references: tuple[str, ...],
    ) -> ProjectIdentity:
        entry = self.registry.by_root(root)
        if entry is None and git is not None:
            entry = (
                self.registry.by_root(git.repository_root)
                or self.registry.by_common_dir(git.git_common_dir)
                or self.registry.by_remote(git.repository_remote)
            )
        if entry is not None:
            return self._identity(
                entry=entry, workspace=root, git=git,
                provider=provider, surface=surface,
                method=method, confidence=confidence, references=references,
            )
        if git is not None:
            if git.repository_remote:
                project_id = _remote_project_id(git.repository_remote)
                project_name = _remote_project_name(git.repository_remote)
            else:
                project_id = _local_project_id(git.git_common_dir, git.repository_root)
                project_name = Path(git.repository_root).name
        elif is_non_project_root(root):
            # A profile, application or provider-state directory is a surface,
            # not a project (ADR-006). Git evidence above already outranks this.
            return self._identity(
                project_id=f"unclassified/{provider}",
                project_name=f"Unclassified ({provider})",
                workspace=root, git=None, provider=provider, surface=surface,
                method="unclassified_provider", confidence=0.0,
                references=references,
            )
        else:
            project_id = _declared_root_project_id(root)
            project_name = Path(root).name
        return self._identity(
            project_id=project_id, project_name=project_name,
            workspace=root, git=git, provider=provider, surface=surface,
            method=method, confidence=confidence, references=references,
        )

    @staticmethod
    def _valid_directory(value: str | os.PathLike[str] | None) -> str | None:
        if value is None or not os.fspath(value).strip():
            return None
        try:
            path = Path(value)
            if path.is_file():
                path = path.parent
            if not path.is_dir():
                return None
            return _path_display(path)
        except (OSError, ProjectIdentityError):
            return None

    def _run_git(self, cwd: str, *args: str) -> str | None:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=cwd,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.git_timeout,
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None

    def _inspect_git(self, workspace: str | None) -> _GitEvidence | None:
        if workspace is None:
            return None
        root = self._run_git(workspace, "rev-parse", "--show-toplevel")
        if root is None:
            return None
        common_dir = self._run_git(
            workspace, "rev-parse", "--path-format=absolute", "--git-common-dir"
        )
        if common_dir is None:
            raw_common = self._run_git(workspace, "rev-parse", "--git-common-dir")
            if raw_common is None:
                return None
            common_dir = str((Path(root) / raw_common).resolve(strict=False))
        branch = self._run_git(workspace, "symbolic-ref", "--short", "-q", "HEAD")
        remote = normalize_git_remote(
            self._run_git(workspace, "config", "--get", "remote.origin.url")
        )
        root_display = _path_display(root)
        common_display = _path_display(common_dir)
        return _GitEvidence(
            repository_root=root_display,
            git_common_dir=common_display,
            repository_remote=remote,
            branch=branch,
            worktree_name=Path(root_display).name,
        )

    def _resolve_references(self, references: Iterable[str] | None) -> tuple[str, ...]:
        resolved: list[str] = []
        seen: set[str] = set()
        for raw in references or ():
            if not isinstance(raw, str) or not raw.strip():
                continue
            clean = raw.strip()
            entry = self.registry.by_alias(clean)
            value = entry.project_id if entry else clean
            key = value.casefold()
            if key not in seen:
                seen.add(key)
                resolved.append(value)
        return tuple(resolved)

    @staticmethod
    def _identity(
        *,
        provider: str,
        surface: str,
        method: str,
        confidence: float,
        references: tuple[str, ...],
        workspace: str | None,
        git: _GitEvidence | None,
        entry: ProjectAlias | None = None,
        project_id: str | None = None,
        project_name: str | None = None,
    ) -> ProjectIdentity:
        resolved_id = entry.project_id if entry is not None else project_id
        if resolved_id is None:
            raise ProjectIdentityError("resolver produced no project_id")
        resolved_name = (
            project_name.strip()
            if isinstance(project_name, str) and project_name.strip()
            else entry.project_name
            if entry is not None
            else _default_project_name(resolved_id)
        )
        return ProjectIdentity(
            project_id=resolved_id,
            project_name=resolved_name,
            workspace_root=workspace,
            repository_root=git.repository_root if git else None,
            repository_remote=git.repository_remote if git else None,
            git_common_dir=git.git_common_dir if git else None,
            worktree_name=git.worktree_name if git else None,
            branch=git.branch if git else None,
            provider=provider,
            surface=surface,
            resolution_method=method,
            resolution_confidence=confidence,
            referenced_projects=references,
        )

def _slug(value: str) -> str:
    value = str(value).strip().casefold()
    value = re.sub(r"[^a-z0-9._-]+", "-", value)
    return value.strip("-._")


def _stable_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _remote_project_id(remote: str) -> str:
    repository = _slug(remote.rsplit("/", 1)[-1]) or "repository"
    return f"git/{repository}-{_stable_digest(remote)}"


def _remote_project_name(remote: str) -> str:
    return remote.rsplit("/", 1)[-1] or remote


def _local_project_id(common_dir: str, repository_root: str) -> str:
    del repository_root
    return f"local/{_stable_digest(canonical_path_key(common_dir))}"


def _declared_root_project_id(root: str) -> str:
    label = _slug(Path(root).name) or "workspace"
    return f"root/{label}-{_stable_digest(canonical_path_key(root))}"


# Directories that are a profile, an application install or provider state —
# never a project (ADR-006). Real capture on Windows attributed sessions to
# `root/miche-<digest>` (the user's own profile directory),
# `root/microsoft-vs-code-<digest>` (the editor's install directory) and
# `root/workspace-<digest>` (a provider's private state directory). Without git
# evidence or a registry entry, a workspace inside one of these is not a
# project: it resolves to `unclassified/<provider>` instead.
_NON_PROJECT_SUBTREES = (
    ("AppData",),
    ("Library",),
    (".cache",),
    (".config",),
    (".local", "share"),
)

# Temporary directories keep the previous behaviour: they live under AppData on
# Windows, they are where ephemeral workspaces (and the test suite) legitimately
# run, and the "official workspace" contract already gives them a full-path
# identity. The guard targets profile, application and provider-state roots.
_NON_PROJECT_EXEMPT_SUBTREES = (
    ("AppData", "Local", "Temp"),
)

_NON_PROJECT_ABSOLUTE = (
    "c:/program files",
    "c:/program files (x86)",
    "c:/programdata",
    "c:/windows",
    "/usr",
    "/etc",
    "/opt",
    "/var",
    "/library",
    "/applications",
)


def _home_directory() -> Path | None:
    for variable in ("USERPROFILE", "HOME"):
        value = os.environ.get(variable)
        if value and value.strip():
            try:
                return Path(value).expanduser()
            except (OSError, ValueError):
                continue
    return None


def is_non_project_root(root: str | os.PathLike[str] | None) -> bool:
    """True when `root` is a profile, application or provider-state location."""
    if root is None:
        return False
    key = canonical_path_key(root)
    if not key:
        return False

    for prefix in _NON_PROJECT_ABSOLUTE:
        if key == prefix or key.startswith(prefix.rstrip("/") + "/"):
            return True

    home = _home_directory()
    if home is None:
        return False
    home_key = canonical_path_key(home)
    if not home_key:
        return False
    # The profile root itself is a profile, not a project.
    if key == home_key:
        return True
    if not key.startswith(home_key.rstrip("/") + "/"):
        return False

    relative = key[len(home_key.rstrip("/")) + 1:].split("/")

    def _matches(subtree: tuple[str, ...]) -> bool:
        return [part.casefold() for part in relative[: len(subtree)]] == [
            part.casefold() for part in subtree
        ]

    if any(_matches(subtree) for subtree in _NON_PROJECT_EXEMPT_SUBTREES):
        return False
    return any(_matches(subtree) for subtree in _NON_PROJECT_SUBTREES)


def _default_project_name(project_id: str) -> str:
    return project_id.rsplit("/", 1)[-1].replace("-", " ").strip().title()