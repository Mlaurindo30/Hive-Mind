"""Compatibility re-export — project identity lives in the package (D003-R1).

The implementation moved to :mod:`hive_mind.projects.identity`. This module
holds **no copy** of it: it re-exports the canonical names so existing
importers (parsers, capture core, bridge, tests) keep working while they are
migrated to import the native module directly.

Removal: once no caller imports `scripts.capture.project_identity`.
"""
from __future__ import annotations

import sys
from pathlib import Path

# The package lives under src/; make it importable when this shim is reached
# from a plain `scripts/` execution that has not installed the wheel.
_SRC = Path(__file__).resolve().parents[2] / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from hive_mind.projects.identity import (  # noqa: E402,F401
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
