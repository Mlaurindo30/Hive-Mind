# Annex requirements matrix — 2026-07-27

Status: auditoria de cumprimento por fase do anexo `pasted-text-1.txt`

## Regra de leitura

- `PROVEN`: há evidência atual suficiente no host para sustentar o requisito.
- `PARTIAL`: há progresso forte, mas ainda falta prova final do requisito
  literal do anexo.
- `NOT_PROVEN`: o requisito ainda não foi demonstrado no estado atual.

## Matriz por fase

| Fase | Status | Leitura objetiva |
|---|---|---|
| Fase 0 — declarar o que está rodando | `PROVEN` | runtime, branch/HEAD, tasks e processos principais já foram inventariados no host real |
| Fase 1 — preservação completa | `PROVEN` | archive externo, bundle, manifestos, hashes, versões e XMLs das tasks já existem |
| Fase 2 — inventário de todas as cópias | `PARTIAL` | as cópias principais já foram classificadas sem `UNKNOWN`, mas ainda restam worktrees/snapshots para limpeza administrativa posterior |
| Fase 3 — construir o código canônico consolidado | `PARTIAL` | `ACTIVE` já absorveu `DEVELOPMENT`; o runtime ativo é a baseline operacional, mas ainda falta o fechamento explícito da integração consolidada pedida pelo anexo |
| Fase 4 — organização canônica | `PARTIAL` | `D:\Hive-Mind` já é a única raiz operacional provada, porém ainda existem cópias históricas registradas fora da raiz ativa |
| Fase 5 — validação antes do cutover | `PARTIAL` | há contrato/path canônico, `config validate`, `implementation validate`, `compileall` e validação operacional fortes, mas a bateria staging completa do anexo não foi toda reexecutada nesta passada final |
| Fase 6 — cutover de `D:\Hive-Mind` | `PARTIAL` | o runtime real já está em `D:\Hive-Mind`, mas não há prova corrente de um cutover único formal sobre branch consolidada nomeada como o anexo descreve |
| Fase 7 — restaurar e testar todos os providers | `PARTIAL` | há providers `WORKING` no host, mas nem todos os itens/superfícies do anexo foram reprovados com evento novo |
| Fase 8 — retirar cópias antigas do caminho operacional | `PARTIAL` | não há referência operacional ativa a backup/worktree no runtime validado, mas a retirada/remoção administrativa das cópias ainda não foi concluída |
| Fase 9 — resultado final | `NOT_PROVEN` | os relatórios principais existem, mas os critérios literais de conclusão total do anexo ainda não estão todos demonstrados |

## Evidência principal por fase

### Fase 0

- [repository-consolidation.md](D:\Hive-Mind\reports\repository-consolidation.md)
- [consolidated-runtime-state-2026-07-27.json](D:\Hive-Mind\reports\consolidated-runtime-state-2026-07-27.json)

### Fase 1

- `D:\Hive-Mind-Archive\20260727-141434\`
- `hive-mind-all-refs.bundle`
- `process-manifest.json`
- `untracked-manifest.json`
- `config-hashes.json`
- `scheduled-tasks\*.xml`

### Fase 2

- [worktree-inventory-2026-07-27.md](D:\Hive-Mind\reports\worktree-inventory-2026-07-27.md)
- [worktree-disposition-2026-07-27.md](D:\Hive-Mind\reports\worktree-disposition-2026-07-27.md)

### Fase 3

- `development_is_ancestor_of_active = true`
- `development_unique_commits = []`
- [consolidated-baseline-2026-07-27.md](D:\Hive-Mind\reports\consolidated-baseline-2026-07-27.md)

### Fase 4

- `canonical_runtime_paths = true`
- `startup_fallback_present = false`
- `legacy_supervisor_task = protected_compatible_hidden_wrapper`

### Fase 5

- `48 passed` em:
  - `tests/unit/test_windows_install_contract.py`
  - `tests/unit/test_runtime_path_policy.py`
- `exit_code = 0` em:
  - `python -m hive_mind.cli config validate`
  - `python -m hive_mind.cli implementation validate`
  - `python -m compileall D:\Hive-Mind\src D:\Hive-Mind\scripts`
- teste explícito de paths proibidos no contrato Windows do runtime

### Fase 6

- scheduled tasks atuais apontando para `D:\Hive-Mind`
- [post-reboot-validation.json](D:\Hive-Mind\logs\post-reboot-validation.json) com `status = pass`

### Fase 7

- [provider-host-status-2026-07-27.md](D:\Hive-Mind\reports\provider-host-status-2026-07-27.md)
- `validate agents --json`:
  - `WORKING`: `claude`, `codex`, `qwen`, `kimi`, `kilo`, `copilot`, `antigravity`, `hermes`, `mimo`
  - sem prova local suficiente: `openclaw`, `roo`, `screenpipe`, `swarmclaw`

### Fase 8

- [worktree-disposition-2026-07-27.md](D:\Hive-Mind\reports\worktree-disposition-2026-07-27.md)
- `runtime_path_audit.findings = []`

### Fase 9

- relatórios existentes:
  - [repository-consolidation.md](D:\Hive-Mind\reports\repository-consolidation.md)
  - [repository-consolidation.json](D:\Hive-Mind\reports\repository-consolidation.json)
  - [live-provider-capture-recovery.md](D:\Hive-Mind\reports\live-provider-capture-recovery.md)
  - [live-provider-capture-recovery.json](D:\Hive-Mind\reports\live-provider-capture-recovery.json)
- mas ainda sem prova de conclusão literal de todos os critérios do anexo

## Gaps reais remanescentes

1. Fechamento formal da integração consolidada pedida pelo anexo, não só a
   leitura de baseline operacional já consolidada.
2. Decisão final sobre o estado residual da task protegida
   `HiveMind-Supervisor`.
3. Revalidação com evento novo para os itens do bloco de providers ainda sem
   fonte real suficiente no host atual.
4. Limpeza administrativa posterior das cópias/worktrees não operacionais
   ainda registradas.

## Contradição que precisa ser evitada

- “captura voltou” ou “o runtime voltou a operar em `D:\Hive-Mind`” não prova,
  sozinho, “missão concluída”.
- No estado atual, isso prova recuperação operacional real do runtime
  canônico.
- Não prova ainda, por si só, o fechamento literal das Fases 3, 5, 6, 7, 8 e
  9 do anexo.

## Itens que não são mais blockers técnicos reais

- `default/ins`: histórico preservado, não backlog vivo do runtime.
- wrapper protegido do supervisor: restrição residual de bootstrap, não prova
  de runtime concorrente.
