"""Canonical project identity (ADR-006, ADR-013).

`hive_mind.projects.identity` is the single implementation of project
identity resolution. `scripts/capture/project_identity.py` re-exports from
here and holds no copy of the logic (D003-R1).
"""

from hive_mind.projects.identity import (
    DEFAULT_REGISTRY_PATH,
    ProjectAlias,
    ProjectAliasRegistry,
    ProjectIdentity,
    ProjectIdentityError,
    ProjectIdentityResolver,
    RegistryValidationError,
    canonical_path_key,
    is_non_project_root,
    normalize_git_remote,
    validate_project_id,
)

__all__ = [
    "DEFAULT_REGISTRY_PATH",
    "ProjectAlias",
    "ProjectAliasRegistry",
    "ProjectIdentity",
    "ProjectIdentityError",
    "ProjectIdentityResolver",
    "RegistryValidationError",
    "canonical_path_key",
    "is_non_project_root",
    "normalize_git_remote",
    "validate_project_id",
]
