# G4 Windows runtime cutover — 2026-07-28

## Objetivo

Remover o ownership material remanescente de
`scripts/setup/register-windows-runtime.ps1`, deixando o PowerShell apenas como
bootstrap/wrapper e movendo a lógica de produto para uma superfície nativa
Python.

## Mudança aplicada

Owner nativo novo:

- `src/hive_mind/maintenance/windows_runtime.py`

Superfície CLI nova:

- `python -m hive_mind.cli service windows-runtime`

Estado novo do wrapper PowerShell:

- `scripts/setup/register-windows-runtime.ps1`
- apenas resolve `D:\Hive-Mind\.venv\Scripts\python.exe`
- delega para `python -m hive_mind.cli service windows-runtime --json`
- usa `--apply` somente fora de `-WhatIfOnly`

## O que saiu do PowerShell

O wrapper não contém mais:

- catálogo material de tarefas de runtime;
- criação/overwrite direto de scheduled tasks;
- lógica de comparação de task existente;
- regra de compatibilidade do wrapper VBS legado;
- instalação/remoção do fallback em Startup.

Essas regras agora vivem em `hive_mind.maintenance.windows_runtime`.

## Evidência executada em 2026-07-28

Comandos:

- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:\Hive-Mind\scripts\setup\register-windows-runtime.ps1 -Root D:\Hive-Mind -WhatIfOnly`
- `python -m pytest tests/unit/test_windows_install_contract.py tests/unit/test_cutover_owner_contract.py tests/unit/test_implementation_validation.py -q`
- `python -m hive_mind.cli implementation status`
- `python -m hive_mind.cli implementation validate`

Resultados:

- dry-run do wrapper retorna plano JSON via owner nativo com 3 tasks:
  - `HiveMind-Supervisor`
  - `HiveMind-Supervisor-Watchdog`
  - `HiveMind-PostRebootValidation`
- suíte focada de contrato/implementação: `60 passed`
- `implementation validate`: documentos consistentes com o repositório
- `implementation status`: `LEGACY_OWNER = 13`

## Reclassificação comprovada

Na matriz viva `docs/implementation/WINDOWS-NATIVE-MIGRATION.md`:

- `scripts/setup/register-windows-runtime.ps1` foi reclassificado para `THIN_WRAPPER`
- `LEGACY_OWNER` caiu de `14` para `13`

## Conclusão

No corte de terça-feira, 28 de julho de 2026:

- `register-windows-runtime.ps1` não sustenta mais `LEGACY_OWNER`;
- o ownership material desse fluxo foi movido para Python nativo;
- G4 global continua `PARTIAL`, porque ainda restam outros owners legados reais
  fora deste componente.
