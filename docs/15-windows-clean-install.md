# Windows clean-install acceptance

This is the acceptance path for a native Windows installation. It treats a
running process as insufficient evidence: every required service for the
selected profile must report `healthy`.

## Profiles

`local-min` runs the local SQLite/vector path and requires the baseline runtime
services. `local-full` also requires Docker Desktop, Milvus, RAGFlow, FalkorDB,
and Syncthing. The installer starts the full-stack containers and Syncthing,
then blocks on their readiness. It exits non-zero if any required service does
not become healthy.

## Clean machine procedure

1. Clone the repository to a writable local path and open PowerShell.
2. Run `install.bat --profile local-min --install-prerequisites` for the
   baseline installation, or select `local-full` when Docker-backed services
   are required.
3. Confirm `node npm/bin/hive-mind.js services status` exits zero. It prints
   the state for every selected service and exits non-zero when a required one
   is not healthy.
4. Run `node npm/bin/hive-mind.js doctor`. It exits zero only when both the API
   and all required services are healthy.
5. Reboot Windows. After sign-in, inspect
   `logs/post-reboot-validation.json`. A passing report contains the selected
   profile, the required service list, and an empty
   `unhealthy_required_services` list.

The scheduled post-reboot validation deliberately fails when the supervisor
manifest or its state file is missing. Optional services do not make a passing
required-service report fail.

## Development and release checks

Run the following before a release candidate:

```powershell
python scripts/release/validate_package.py --source-root .
./tests/install/test_windows_bootstrap.ps1
install.bat --profile local-min --dry-run
install.bat --profile local-full --dry-run
node --test npm/test/supervisor.test.js npm/test/doctor.test.js
```

The release validator requires `pyproject.toml`, `npm/package.json`, and
`core/version.py` to agree. The `Windows Installer Contracts` workflow runs
these offline checks on `windows-latest`; it does not claim Docker or reboot
acceptance. A real `local-full` acceptance still requires Docker Desktop to be
available and an actual reboot on the target machine.
