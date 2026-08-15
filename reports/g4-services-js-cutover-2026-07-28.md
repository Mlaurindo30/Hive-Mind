# G4 — cutover de `npm/lib/services.js` para wrapper derivado do manifest

Data: 2026-07-28

## Resultado

`npm/lib/services.js` deixou de manter catálogo hardcoded de systemd/launchd e
agora deriva as units gerenciadas a partir do manifest canônico via
`npm/lib/supervisor.js`.

## Arquivos alterados

- `D:\Hive-Mind\npm\lib\services.js`
- `D:\Hive-Mind\tests\unit\test_service_catalog_parity.py`
- `D:\Hive-Mind\docs\implementation\WINDOWS-NATIVE-MIGRATION.md`

## Mudança objetiva

Antes:

- `services.js` mantinha `SYSTEMD_UNITS = [...]`;
- isso criava um terceiro catálogo concorrente de serviços.

Depois:

- `services.js` usa `supervisor.loadManifest()` +
  `supervisor.runnableServices(manifest)` para calcular `managedUnits()`;
- `systemd()` e `launchd()` operam sobre essa lista derivada;
- o arquivo passa a ser wrapper de dispatch, não owner de catálogo.

## Evidência de validação

Comandos executados:

```powershell
$env:PYTHONPATH='D:\Hive-Mind\src'
.\.venv\Scripts\python.exe -m pytest `
  tests\unit\test_service_catalog_parity.py `
  tests\unit\test_implementation_validation.py `
  tests\unit\test_windows_install_contract.py `
  tests\unit\test_cutover_owner_contract.py -q

.\.venv\Scripts\python.exe -m hive_mind.cli implementation validate
.\.venv\Scripts\python.exe -m hive_mind.cli implementation status
```

Resultados:

- `68 passed in 13.93s`
- `implementation documents: consistent with the repository`
- `LEGACY_OWNER = 11`

## Impacto no gate

- `npm/lib/services.js` foi reclassificado para `THIN_WRAPPER`;
- o inventário de `LEGACY_OWNER` caiu de `12` para `11`.
