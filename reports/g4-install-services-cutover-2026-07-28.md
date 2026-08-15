# G4 — cutover de `scripts/setup/install_services.py` para owner nativo

Data: 2026-07-28

## Resultado

O catálogo/manifesto operacional de serviços saiu de
`scripts/setup/install_services.py` e foi portado para
`src/hive_mind/maintenance/runtime_services.py`.

O arquivo legado agora é apenas um shim de compatibilidade.

## Arquivos alterados

- `D:\Hive-Mind\src\hive_mind\maintenance\runtime_services.py`
- `D:\Hive-Mind\scripts\setup\install_services.py`
- `D:\Hive-Mind\src\hive_mind\cli.py`
- `D:\Hive-Mind\src\hive_mind\install\windows.py`
- `D:\Hive-Mind\tests\unit\test_install_services.py`
- `D:\Hive-Mind\tests\unit\test_service_backends.py`
- `D:\Hive-Mind\tests\unit\test_manifest_job_parity.py`
- `D:\Hive-Mind\tests\unit\test_service_catalog_parity.py`
- `D:\Hive-Mind\docs\implementation\WINDOWS-NATIVE-MIGRATION.md`

## Mudança objetiva

Antes:

- `scripts/setup/install_services.py` concentrava:
  - `unit_definitions()`
  - `service_specs()`
  - `manifest()`
  - instalação/check/launchd/post-reboot
- código Python nativo ainda chamava esse script por caminho legado.

Depois:

- o owner nativo é `hive_mind.maintenance.runtime_services`;
- `scripts/setup/install_services.py` ficou com 12 linhas e só reexporta
  `main()` e helpers do módulo nativo;
- foi adicionada a superfície:

```powershell
python -m hive_mind.cli service manifest --json
```

- `src/hive_mind/install/windows.py` deixou de invocar o script legado e passa
  a usar a CLI nativa.

## Evidência objetiva

- `rg -n "install_services\\.py" D:\Hive-Mind\src` → sem ocorrências
- `scripts/setup/install_services.py` → 12 linhas
- `python -m hive_mind.cli service manifest --json` → manifesto emitido com
  `manifest_version = 2`

## Validação executada

```powershell
$env:PYTHONPATH='D:\Hive-Mind\src'
.\.venv\Scripts\python.exe -m pytest `
  tests\unit\test_install_services.py `
  tests\unit\test_service_backends.py `
  tests\unit\test_manifest_job_parity.py `
  tests\unit\test_service_catalog_parity.py `
  tests\unit\test_implementation_validation.py `
  tests\unit\test_windows_install_contract.py `
  tests\unit\test_cutover_owner_contract.py -q

.\.venv\Scripts\python.exe -m hive_mind.cli implementation validate
.\.venv\Scripts\python.exe -m hive_mind.cli implementation status
```

Resultados:

- `92 passed, 2 skipped in 14.32s`
- `implementation documents: consistent with the repository`
- `LEGACY_OWNER = 10`

## Impacto no gate

- `scripts/setup/install_services.py` foi reclassificado para `THIN_WRAPPER`
- `LEGACY_OWNER` caiu de `11` para `10`
