# Windows Full Bootstrap Design

## Goal

Make `install.ps1 -Profile local-full` capable of taking a clean Windows host
to a working Hive-Mind full installation, while preserving an existing vault,
UMC database, environment file, and agent MCP configuration.

## Scope

The installer will provision or validate Git, uv, Bun, Node LTS, Docker Desktop,
Ollama, Rust, Visual Studio Build Tools, and WSL2. It will then create the
Python runtime, start the local-full container stack, pull configured Ollama
models, bootstrap integrations, register MCP, and validate the installation.

## Safety and recovery

Before changing the project runtime, the installer creates a timestamped
snapshot with hashes of `cerebro/`, `hive_mind.db`, `.env`, and project-managed
MCP configuration. The snapshot is stored outside `.venv` and is verified before
the install continues. Runtime repair may recreate only `.venv`; it must never
delete, replace, or materialize over existing protected data.

Each prerequisite is detected before installation. Missing packages are
installed through explicit WinGet package IDs with source and package agreements
accepted only for that invocation. The process validates the installed command
or service before proceeding. WSL2 or Docker operations that require a reboot
persist a resume state and stop with an exact continuation command; no later
installation phase runs in a partially rebooted state.

## Installer interface

`install.ps1` will add a prerequisite phase for `local-full` by default and
offer a `-SkipPrerequisites` escape hatch for managed environments. It exposes
an opt-in `-PrerequisitesOnly` mode for diagnosing or pre-provisioning a host.
The normal flow remains idempotent: installed healthy components are not
reinstalled.

## Components

- `scripts/setup/bootstrap-prerequisites.ps1`: detection, package definitions,
  WinGet installation, restart/resume handling, and post-install validation.
- `scripts/setup/backup-install-state.ps1`: consistent SQLite backup plus file
  manifest/hashes for data that must survive runtime repair.
- `install.ps1`: invokes backup first, then prerequisite bootstrap before its
  existing Python, Docker, Ollama, and service phases.
- Tests: PowerShell tests run the bootstrap in a mocked/dry-run mode; they
  assert package selection, idempotence, resume behavior, and that protected
  project data is excluded from cleanup.

## Data flow

`backup -> validate prerequisites -> install missing prerequisites -> restart
if required -> create/repair .venv -> sync dependencies -> start Docker stack
-> pull models -> bootstrap/index -> register MCP -> health/tests`.

## Failure handling

Failure at any phase stops the installer and reports the failed prerequisite or
service. Existing data stays untouched; the verified snapshot supports recovery.
Docker health must be available before `local-full` wrappers or containers are
started. A failed model pull or container startup is reported separately and
does not invalidate the backup.

## Verification

The final validation checks database integrity, vault manifest hashes,
prerequisite versions, Docker engine and compose services, Ollama reachability
and required models, MCP registration, and `sinapse-write.py health`. Unit and
smoke tests validate installer behavior without downloading or installing host
software.
