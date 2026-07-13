# Clean Windows Operational Recovery Design

## Objective

Make `install.ps1 -Profile local-full` a reliable native Windows installation path: provision and verify dependencies, start the full stack, surface real service state, and produce evidence consumable by clean-install and post-reboot validation.

## Boundaries

Hive-Mind code, Python workers, Node supervisor, MCP, vault and SQLite run on the Windows host. Docker Desktop may use WSL2 internally for its Linux engine, but no Hive-Mind process is installed in WSL. `local-min` never requires Docker. `local-full` fails explicitly unless Docker, Milvus, RAGFlow, FalkorDB and Syncthing are ready.

## Design

`install.ps1` remains canonical. A declarative readiness contract gates live `local-full` installation in this order: prerequisites, Docker daemon, compose start, container health, supervisor start, then authenticated operational validation. Required services are never silently removed.

The supervisor remains the owner of workers and reconciles stale persisted state through its managed child PID plus declared probe. Clean-install tests isolate HOME, LOCALAPPDATA, TEMP, vault and database paths. Windows CI calls the canonical underscore-named package validator.

## Acceptance

- Both profiles pass dry-run without mutating runtime data.
- `local-full` fails clearly before Docker is ready and succeeds only when required services are healthy.
- Supervisor state cannot contradict an owned worker's health probe.
- Post-reboot validation reports specific failed services and is tested on Windows.
- CI references tracked paths only.
- A reboot is accepted only after explicit authorization and a green post-reboot artifact.

