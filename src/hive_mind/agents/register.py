"""Register the Hive-Mind MCP server with detected providers (ADR-013).

Maps each provider to its config target(s) — ported from the per-provider
registrars in register-mcp.ps1 — and applies the transactional merge from
`mcp_config`. Defaults to dry-run at every call site that inspects, so nothing
is mutated unless the caller explicitly asks.

TOML targets (Codex's `config.toml`) are reported as unsupported rather than
skipped silently; a TOML writer is a separate slice.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from hive_mind.agents.mcp_config import build_stdio_entry, merge_mcp_config
from hive_mind.agents.registry import ConfigTarget, ProviderSpec, get_provider

SERVER_NAME = "sinapse-memory"


@dataclass(frozen=True)
class RegistrationResult:
    provider: str
    path: str
    kind: str
    changed: bool
    supported: bool = True
    backup: Optional[str] = None
    note: Optional[str] = None


def _resolve(target: ConfigTarget, home: Path, appdata: Path, project_root: Path) -> Path:
    roots = {"home": home, "appdata": appdata, "project": project_root}
    try:
        base = roots[target.base]
    except KeyError:  # pragma: no cover - registry is closed
        raise ValueError(f"unknown config base: {target.base}")
    return base / target.path


def register_providers(
    provider_ids: Iterable[str],
    *,
    home: Path,
    appdata: Path,
    project_root: Path,
    python: str,
    server: str,
    dry_run: bool = True,
) -> list[RegistrationResult]:
    """Register the MCP server for each provider. Dry-run by default."""
    home, appdata, project_root = Path(home), Path(appdata), Path(project_root)
    results: list[RegistrationResult] = []

    for provider_id in provider_ids:
        spec: ProviderSpec = get_provider(provider_id)  # raises KeyError if unknown
        for target in spec.configs:
            path = _resolve(target, home, appdata, project_root)
            if target.kind == "toml":
                from hive_mind.agents.toml_config import (
                    build_codex_entry,
                    merge_codex_config,
                )

                merged_toml = merge_codex_config(
                    path,
                    SERVER_NAME,
                    build_codex_entry(python, server, str(project_root)),
                    dry_run=dry_run,
                )
                results.append(
                    RegistrationResult(
                        provider=spec.id,
                        path=merged_toml.path,
                        kind="toml",
                        changed=merged_toml.changed,
                        backup=merged_toml.backup,
                    )
                )
                continue

            entry = build_stdio_entry(python, server, str(project_root))
            if target.stdio_type:
                entry["type"] = "stdio"
            merged = merge_mcp_config(
                path,
                SERVER_NAME,
                entry,
                root_key=target.root_key,
                dry_run=dry_run,
            )
            results.append(
                RegistrationResult(
                    provider=spec.id,
                    path=merged.path,
                    kind="json",
                    changed=merged.changed,
                    backup=merged.backup,
                )
            )
    return results
