"""Diagnose and unregister agent integrations (D009-R5).

`doctor` answers, per provider: is it installed, is the MCP server registered
in each of its config targets, and is the instruction block present. It is
read-only.

`unregister` is the inverse of `register`: it removes the Hive-Mind server
entry from the provider's configs and, optionally, the managed instruction
block — leaving every third-party entry and everything the user wrote alone.
It is dry-run by default, like `register`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from hive_mind.agents.detect import detect_providers
from hive_mind.agents.instructions import has_managed_block, remove_instructions
from hive_mind.agents.register import SERVER_NAME, _resolve
from hive_mind.agents.registry import PROVIDERS, ProviderSpec, get_provider


@dataclass(frozen=True)
class ConfigDiagnosis:
    path: str
    kind: str
    exists: bool
    registered: bool


@dataclass(frozen=True)
class ProviderDiagnosis:
    provider: str
    name: str
    detected: bool
    configs: list[ConfigDiagnosis] = field(default_factory=list)
    instruction_path: Optional[str] = None
    instructions_installed: bool = False

    @property
    def fully_registered(self) -> bool:
        return bool(self.configs) and all(c.registered for c in self.configs)

    @property
    def healthy(self) -> bool:
        """A detected provider is healthy when everything it needs is in place."""
        if not self.detected:
            return True  # nothing to configure for an absent agent
        if not self.fully_registered:
            return False
        if self.instruction_path and not self.instructions_installed:
            return False
        return True


def _is_registered(path: Path, kind: str, root_key: str) -> bool:
    if kind == "toml":
        from hive_mind.agents.toml_config import is_registered as toml_registered

        return toml_registered(path, SERVER_NAME)
    from hive_mind.agents.mcp_config import is_registered as json_registered

    return json_registered(path, SERVER_NAME, root_key)


def diagnose(
    provider_ids: Optional[Iterable[str]] = None,
    *,
    home: Path,
    appdata: Path,
    project_root: Path,
    which=None,
) -> list[ProviderDiagnosis]:
    """Read-only diagnosis of every requested provider.

    `which` is injectable so a diagnosis can be run against a synthetic
    environment; otherwise the host's real PATH leaks into the result.
    """
    home, appdata, project_root = Path(home), Path(appdata), Path(project_root)
    detected = {
        r.id: r.detected
        for r in detect_providers(home=home, appdata=appdata, which=which)
    }
    specs: list[ProviderSpec] = (
        [get_provider(p) for p in provider_ids] if provider_ids else list(PROVIDERS)
    )

    results = []
    for spec in specs:
        configs = []
        for target in spec.configs:
            path = _resolve(target, home, appdata, project_root)
            configs.append(
                ConfigDiagnosis(
                    path=str(path), kind=target.kind, exists=path.is_file(),
                    registered=_is_registered(path, target.kind, target.root_key),
                )
            )
        instruction_path = (
            str(project_root / spec.prompt_target) if spec.prompt_target else None
        )
        results.append(
            ProviderDiagnosis(
                provider=spec.id,
                name=spec.name,
                detected=detected.get(spec.id, False),
                configs=configs,
                instruction_path=instruction_path,
                instructions_installed=(
                    has_managed_block(instruction_path) if instruction_path else False
                ),
            )
        )
    return results


@dataclass(frozen=True)
class UnregisterResult:
    provider: str
    path: str
    kind: str
    changed: bool
    backup: Optional[str] = None


def unregister_providers(
    provider_ids: Iterable[str],
    *,
    home: Path,
    appdata: Path,
    project_root: Path,
    dry_run: bool = True,
    remove_instruction_block: bool = False,
) -> list[UnregisterResult]:
    """Remove the Hive-Mind entry from each provider's configs. Dry-run default."""
    home, appdata, project_root = Path(home), Path(appdata), Path(project_root)
    results: list[UnregisterResult] = []

    for provider_id in provider_ids:
        spec = get_provider(provider_id)
        for target in spec.configs:
            path = _resolve(target, home, appdata, project_root)
            if target.kind == "toml":
                from hive_mind.agents.toml_config import remove_from_codex_config

                removed = remove_from_codex_config(path, SERVER_NAME, dry_run=dry_run)
            else:
                from hive_mind.agents.mcp_config import remove_mcp_config

                removed = remove_mcp_config(
                    path, SERVER_NAME, target.root_key, dry_run=dry_run
                )
            results.append(
                UnregisterResult(spec.id, removed.path, target.kind,
                                 removed.changed, removed.backup)
            )
        if remove_instruction_block and spec.prompt_target:
            instruction = remove_instructions(
                spec.id, project_root / spec.prompt_target, dry_run=dry_run
            )
            results.append(
                UnregisterResult(spec.id, instruction.path, "instructions",
                                 instruction.changed, instruction.backup)
            )
    return results
