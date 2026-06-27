"""Shared vault indexing exclusions for filesystem and graph scanners."""

from __future__ import annotations

from pathlib import Path


EXCLUDED_VAULT_DIR_NAMES = {
    ".claude",
    ".claude-flow",
    ".codex",
    ".gemini",
    ".github",
    ".obsidian",
    ".openclaw",
    ".roo",
    ".smart-env",
    ".trash",
    "Chats",
    "copilot",
    "attachments",
    "__pycache__",
}

EXCLUDED_VAULT_REL_PREFIXES = {
    "graphify-out",
    "cortex/occipital/grafo/graphify-out",
    "tronco/infra/agentes",
    "tronco/infra/obsidian-trash",
}


def normalized_rel(path: str | Path) -> str:
    return Path(path).as_posix().strip("/")


def is_excluded_vault_rel(path: str | Path) -> bool:
    rel = normalized_rel(path)
    if not rel:
        return False
    parts = Path(rel).parts
    if any(part in EXCLUDED_VAULT_DIR_NAMES for part in parts):
        return True
    return any(rel == prefix or rel.startswith(f"{prefix}/") for prefix in EXCLUDED_VAULT_REL_PREFIXES)


def filter_walk_dirs(root: str | Path, dirs: list[str], vault_root: str | Path) -> None:
    """Mutate ``dirs`` in-place so os.walk skips vault noise consistently."""
    root_path = Path(root)
    vault = Path(vault_root)
    kept: list[str] = []
    for name in dirs:
        try:
            rel = (root_path / name).relative_to(vault)
        except ValueError:
            rel = Path(name)
        if name in EXCLUDED_VAULT_DIR_NAMES or is_excluded_vault_rel(rel):
            continue
        kept.append(name)
    dirs[:] = kept
