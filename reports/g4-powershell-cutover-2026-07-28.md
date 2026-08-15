# G4 PowerShell cutover follow-up — 2026-07-28

## Objetivo

Revalidar no estado atual do repositório o gate G4 do anexo de remediação,
focado nos dois componentes explicitamente citados:

- `install.ps1`
- `scripts/setup/register-windows-jobs.ps1`

## Evidência atual

Arquivos lidos no host em 28 de julho de 2026:

- `D:\Hive-Mind\install.ps1`
- `D:\Hive-Mind\scripts\setup\register-windows-jobs.ps1`
- `D:\Hive-Mind\src\hive_mind\install\windows.py`
- `D:\Hive-Mind\src\hive_mind\maintenance\windows_jobs.py`

Estado observado:

- `install.ps1` tem `80` linhas e apenas:
  - resolve um Python de bootstrap;
  - repassa flags;
  - delega para `scripts/setup/native_windows_install.py`
- `scripts/setup/register-windows-jobs.ps1` tem `18` linhas e apenas:
  - resolve `D:\Hive-Mind\.venv\Scripts\python.exe`;
  - delega para `python -m hive_mind.cli service windows-jobs`

Nenhum dos dois mantém mais:

- catálogo material de jobs;
- registro direto de scheduled tasks;
- `uv sync`, `docker compose`, bootstrap completo ou ownership principal de instalação.

## Validação executada

Comandos:

- `python -m pytest tests/unit/test_windows_install_contract.py tests/unit/test_windows_backup_task_migration.py tests/unit/test_cutover_owner_contract.py tests/unit/test_manifest_job_parity.py -q`
- `python -m pytest tests/unit/test_implementation_validation.py -q`
- `python -m hive_mind.cli implementation validate`
- `python -m hive_mind.cli implementation status`

Resultados:

- suíte de cutover/owner Windows: `41 passed`
- validação de implementação: `30 passed`
- `implementation validate`: documentos consistentes com o repositório
- `implementation status`: `LEGACY_OWNER = 14`

## Reclassificação comprovada

Na matriz viva `docs/implementation/WINDOWS-NATIVE-MIGRATION.md`:

- `install.ps1` foi reclassificado para `THIN_WRAPPER`
- `scripts/setup/register-windows-jobs.ps1` foi reclassificado para `THIN_WRAPPER`
- o total de `LEGACY_OWNER` caiu de `16` para `14`

## Conclusão

No corte de 28 de julho de 2026:

- os dois componentes explicitamente citados no anexo para G4 já não sustentam
  `PRODUCT_LOGIC` nem `LEGACY_OWNER`;
- G4 global ainda não é `PASS`, porque ainda restam outros owners legados no
  inventário Windows (`register-windows-runtime.ps1`, `npm/lib/supervisor.js`,
  `install_services.py`, entre outros);
- a leitura conservadora correta agora é:
  - `G4` não deve continuar classificado como `FAIL` pelos dois componentes do
    anexo;
  - o estado atual sustentado por evidência é `PARTIAL`.
