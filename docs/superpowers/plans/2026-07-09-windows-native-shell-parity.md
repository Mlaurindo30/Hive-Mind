# Windows native shell parity

## Goal

Create native PowerShell counterparts for the Bash entrypoints used by Hive-Mind, keeping Linux/macOS `.sh` support intact and making Windows installs/editing work directly from `G:\Hive-Mind` with the project-local `.venv`.

## Findings

- `install.sh` is the canonical installer. It creates `.env`, bootstraps pinned integrations, syncs Python dependencies with `uv`, initializes UMC, materializes `cerebro/`, builds Graphify/HNSW, registers MCP, installs hooks, configures services, and writes an install report.
- Existing npm Windows support is partial: it creates `.env`, runs `uv`, registers MCP with `.venv\Scripts\python.exe`, and starts a Node supervisor, but service commands still come from Python manifests that reference `.venv/bin` and `.sh`.
- Several Python scripts assume POSIX paths, especially `scripts/services/sinapse-write.py` and `scripts/setup/install_services.py`.
- The repository has 29 `.sh` files. Windows support should include `.ps1` peers for operational scripts, tests, setup, services, capture hooks, maintenance, and install wrappers.

## Implementation

1. Add shared PowerShell helpers in `scripts/lib/HiveMind.Windows.psm1`.
2. Add `install.ps1` as the Windows-native installer that follows the same order as `install.sh`, while using `.venv\Scripts`.
3. Add `.ps1` counterparts for existing `.sh` entrypoints.
4. Patch Python service path assumptions for Windows.
5. Add/adjust lightweight tests or static checks for Windows script parity where practical.
6. Verify with PowerShell syntax parsing and targeted Python checks without requiring unavailable external tools.
