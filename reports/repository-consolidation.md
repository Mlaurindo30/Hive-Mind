# Repository consolidation status — 2026-07-27

Status: em andamento

## Atualização validada em 2026-07-27 — Fase 0 do host real após saneamento do legado

### Escopo ativo confirmado pelo anexo

A prioridade operacional vigente não é mais só correção de captura isolada.
O anexo `pasted-text-1.txt` redefine a missão para:

- consolidar o projeto numa única raiz canônica;
- atualizar o runtime real `D:\Hive-Mind`;
- retirar `backups/worktrees` do caminho operacional;
- preservar antes de qualquer cutover;
- só depois restaurar e revalidar todos os providers.

### Git do runtime ativo no host

| Campo | Valor |
|---|---|
| Root | `D:\Hive-Mind` |
| Branch | `codex/universal-provider-capture` |
| HEAD | `52a8441b3b661c15a9385a98d042f2e3c70d0277` |

### Worktree de desenvolvimento explicitamente citada no anexo

| Campo | Valor |
|---|---|
| Root | `D:\Hive-Mind\backups\worktrees\hive-mind-windows-zero-install` |
| Branch | `codex/control-plane-redesign` |
| HEAD | `315befe40856f476734440a5bf3819bc47e993b4` |

### Processos Hive-Mind encontrados no host real

| Componente | PID | Command line | Observação |
|---|---:|---|---|
| capture-realtime | `41912` | `D:\Hive-Mind\.venv\Scripts\python.exe D:\Hive-Mind\scripts\capture\capture-realtime.py` | runtime canônico |
| capture-realtime | `38732` | `uv python ... D:\Hive-Mind\scripts\capture\capture-realtime.py` | duplicado fora da `.venv` |
| graphify watch | `7716` | `D:\Hive-Mind\.venv\Scripts\python.exe -m graphify watch D:\Hive-Mind\cerebro` | runtime canônico |
| graphify watch | `40784` | `D:\Hive-Mind\.venv\Scripts\python.exe -m graphify watch D:\Hive-Mind\cerebro` | duplicado canônico |
| graphify watch | `13972` | `uv python ... -m graphify watch D:\Hive-Mind\cerebro` | duplicado fora da `.venv` |
| graphify watch | `34968` | `uv python ... -m graphify watch D:\Hive-Mind\cerebro` | duplicado fora da `.venv` |
| supervisor Node | `41960` | `node D:\Hive-Mind\npm\lib\supervisor.js __daemon` | supervisor principal ativo |
| sinapse-mcp stdio | `9156` | `D:\Hive-Mind\.venv\Scripts\python.exe D:/Hive-Mind/scripts/services/sinapse-mcp.py` | runtime canônico |
| sinapse-mcp stdio | `12304` | `uv python ... D:/Hive-Mind/scripts/services/sinapse-mcp.py` | duplicado fora da `.venv` |
| API | `39744` | `D:\Hive-Mind\.venv\Scripts\python.exe D:\Hive-Mind\scripts\services\sinapse-api.py` | runtime canônico |
| API | `20012` | `uv python ... D:\Hive-Mind\scripts\services\sinapse-api.py` | duplicado fora da `.venv` |
| MCP HTTP | `39404` | `D:\Hive-Mind\.venv\Scripts\python.exe D:\Hive-Mind\scripts\services\sinapse-mcp-http.py` | runtime canônico |
| MCP HTTP | `39100` | `uv python ... D:\Hive-Mind\scripts\services\sinapse-mcp-http.py` | duplicado fora da `.venv` |
| sqlite-vec worker | `39796` | `D:\Hive-Mind\.venv\Scripts\python.exe D:\Hive-Mind\plugins\sqlite-vec-worker\worker.py` | runtime canônico |
| sqlite-vec worker | `41396` | `uv python ... D:\Hive-Mind\plugins\sqlite-vec-worker\worker.py` | duplicado fora da `.venv` |
| otel collector | `39256` | `D:\Hive-Mind\.venv\Scripts\python.exe D:\Hive-Mind\scripts\services\otel_collector.py --host 127.0.0.1` | runtime canônico |
| otel collector | `27740` | `uv python ... D:\Hive-Mind\scripts\services\otel_collector.py --host 127.0.0.1` | duplicado fora da `.venv` |
| watcher launcher | `38284` | `powershell.exe ... D:\Hive-Mind\scripts\services\start-watcher.ps1` | launcher ativo do watcher |
| Claude Mem worker | `30292` | `bun ... claude-mem\\13.12.4\\scripts\\worker-service.cjs --daemon` | fora da raiz Hive-Mind |
| Claude Mem MCP servers | múltiplos | `node ... claude-mem\\13.12.4\\scripts\\mcp-server.cjs` | múltiplas instâncias vivas |

### Tarefas agendadas Hive-Mind ativas no host

| Task | Execute | Arguments |
|---|---|---|
| `HiveMind-Backup` | `D:\Hive-Mind\.venv\Scripts\hive-mind.exe` | `backup run --apply` |
| `HiveMind-ClaudeMemBridge` | `D:\Hive-Mind\.venv\Scripts\python.exe` | `D:\Hive-Mind\scripts\services\claude_mem_bridge.py` |
| `HiveMind-DreamCycle` | `D:\Hive-Mind\.venv\Scripts\python.exe` | `D:\Hive-Mind\scripts\dream\dream_cycle.py` |
| `HiveMind-KnowledgeHealth` | `D:\Hive-Mind\.venv\Scripts\python.exe` | `D:\Hive-Mind\scripts\health\audit_memory.py` |
| `HiveMind-PostRebootValidation` | `D:\Hive-Mind\.venv\Scripts\python.exe` | `D:\Hive-Mind\scripts\health\validate_after_reboot_windows.py` |
| `HiveMind-Supervisor` | `wscript.exe` | `D:\Hive-Mind\scripts\setup\start-windows-supervisor-hidden.vbs D:\Hive-Mind` |
| `HiveMind-Supervisor-Watchdog` | `powershell.exe` | `D:\Hive-Mind\scripts\setup\start-windows-supervisor-watchdog.ps1 -Root D:\Hive-Mind` |

### Referências ainda encontradas a backup/worktree

Evidência operacional/configuracional ainda presente:

- `config/project-aliases.yaml` contém alias explícito para `D:\Hive-Mind\backups\worktrees\hive-mind-windows-zero-install`;
- o próprio `git worktree list --porcelain` ainda registra:
  - `D:\Hive-Mind\backups\worktrees\hive-mind-windows-zero-install`
  - `D:\Hive-Mind-Consolidation\20260722-201726\repo`
  - `D:\Hive-Mind-Dev\runtime-consolidation-final`
- há referências documentais antigas em `reports/repository-consolidation.*`, `reports/staging-gate.md` e `reports/live-provider-capture-recovery.json`.

### Estado do legado após a limpeza controlada já aplicada

Validação atual do banco real:

- `capture_outbox.total = 0`
- `legacy.unclassified_legacy = 0`
- `legacy.default_workspace = 537`
- `legacy.default_active_by_project = ins: 139`

Isto significa:

- o backlog histórico inseguro já não está no caminho operacional;
- o resíduo `unclassified/legacy` do UMC foi zerado;
- o bloco `default/ins` continua preservado e ainda exige decisão de migração separada.

### Evidência adicional sobre `default/ins`

Auditoria read-only executada em 27 de julho de 2026:

- as `139` linhas ativas de `default/ins` no UMC pertencem a uma única sessão;
- `memory_session_id`:
  `openrouter-019f6b7a-98a8-7e22-85b8-661bbcee3d91-1784228743493`;
- `sdk_sessions.project = ins`;
- `platform_source = codex`;
- `user_prompt = "Instale para voce npx agentic-awesome-skills --codex"`;
- janela da sessão:
  `2026-07-16T15:15:22.648Z` → `2026-07-16T15:20:50.393Z`;
- o registry atual não contém alias canônico para `ins`.

Conclusão:

- `default/ins` não é fila viva nem sobra operacional do runtime restaurado;
- é um bloco histórico de label livre preservado de propósito;
- migrar esse bloco hoje exigiria adivinhação, o que contraria o contrato do
  reconciliador controlado.

### Conclusão operacional desta atualização

O runtime real já está concentrado em `D:\Hive-Mind`, mas ainda não há estado
canônico limpo para cutover porque:

1. existem processos duplicados rodando por `.venv` e por `uv`;
2. existem worktrees/snapshots ainda registradas no caminho operacional;
3. há alias/configuração apontando para worktree de backup;
4. os relatórios existentes ainda misturam snapshots antigos com o estado atual.

## Atualização validada em 2026-07-27 — comparação ACTIVE versus DEVELOPMENT

### Resultado objetivo da comparação Git

Comparação executada entre:

- `ACTIVE = 52a8441b3b661c15a9385a98d042f2e3c70d0277`
- `DEVELOPMENT = 315befe40856f476734440a5bf3819bc47e993b4`

Resultado:

- `git merge-base ACTIVE DEVELOPMENT = 315befe40856f476734440a5bf3819bc47e993b4`
- `DEVELOPMENT..ACTIVE` contém commits operacionais relevantes;
- `ACTIVE..DEVELOPMENT` está vazio.

Conclusão direta:

- a worktree `codex/control-plane-redesign` é ancestral da branch ativa;
- hoje não há commits exclusivos na worktree de desenvolvimento a resgatar;
- a consolidação não é um merge entre duas linhas divergentes;
- a consolidação real agora é:
  1. preservar o overlay local do runtime ativo;
  2. eliminar paths/owners duplicados;
  3. preparar um cutover limpo a partir da raiz ativa.

### Commits operacionais já absorvidos pela branch ativa

Entre os commits à frente de `DEVELOPMENT`, os mais relevantes para o cutover atual são:

- `9303f4e` — rejeita targets de runtime em `.tmp` e `backups`
- `75c022c` — preserva agendamento de backup no cutover nativo Windows
- `4b11db4` — prova marcador fresco pela cadeia real de captura
- `4fd3233` — serializa SeenStore no watcher
- `2833d27` — descobre paths reais de Copilot e Antigravity
- `94dde2d` — preserva identidade de workspace do Copilot
- `8f325bf` / `0f864d2` — endurecem/enforçam paths canônicos de operação
- `349418c` — resolve installer Windows a partir do checkout atual

### Overlay local do runtime ativo que ainda não pode se perder

O estado do host mostra que o risco maior agora está nas mudanças locais ainda
não commitadas sobre `ACTIVE`. Áreas críticas:

| Área | Arquivos principais | Motivo |
|---|---|---|
| identidade e ingestão | `src/hive_mind/capture/identity_store.py`, `src/hive_mind/capture/ingest.py` | upgrades de identidade, bridge imediato e correção de replay |
| bridge/Claude Mem | `core/knowledge/claude_mem_bridge.py`, `scripts/setup/sync-claude-mem-provider.py`, `scripts/services/claude-mem-local.ps1` | observações/summaries recentes e self-heal do schema |
| runtime/supervisor Windows | `npm/lib/supervisor.js`, `scripts/setup/register-windows-runtime.ps1`, `scripts/setup/start-windows-supervisor.ps1`, `scripts/setup/apply-hidden-supervisor-task.ps1`, `scripts/setup/start-windows-supervisor-watchdog.ps1` | cutover, singleton bootstrap, owners e tasks |
| captura/provider discovery | `scripts/capture/capture-realtime.py`, `scripts/capture/parsers/antigravity.py` | descoberta real de source path e captura ao vivo |
| validação/canary | `src/hive_mind/validation/canary.py`, `src/hive_mind/validation/delivery.py`, `tests/unit/test_validation_canary.py`, `tests/unit/test_windows_install_contract.py` | prova operacional do runtime e contratos Windows |
| saneamento legado controlado | `src/hive_mind/maintenance/historical_outbox.py`, `src/hive_mind/maintenance/legacy_migration.py`, `src/hive_mind/cli.py` | limpeza controlada já aplicada no host real |

### Arquivos untracked que entram no pacote de consolidação

Os seguintes untracked atuais não são ruído óbvio; fazem parte do trabalho
ativo e precisam ser classificados explicitamente na consolidação:

- `reports/live-provider-capture-recovery.md`
- `reports/repository-consolidation.md`
- `reports/repository-consolidation.json`
- `scripts/setup/start-windows-supervisor-watchdog.ps1`
- `scripts/maintenance/backup.py`
- `src/hive_mind/maintenance/historical_outbox.py`
- `src/hive_mind/maintenance/legacy_migration.py`
- `tests/unit/test_backup_wrapper.py`
- `tests/unit/test_claude_mem_bridge_recent_first.py`
- `tests/unit/test_historical_outbox.py`
- `tests/unit/test_legacy_migration.py`
- `tests/unit/test_legacy_umc_migration.py`

Itens ainda não classificados como operacionais:

- `.cursor/rules/hive-mind.md`
- `integrations/integrations.zip`
- `scripts/release/__init__.py`
- `specs/control-plane-redesign.md`

### Implicação para a próxima fase

O próximo bloco tecnicamente correto é construir a integração canônica a partir
de `D:\Hive-Mind` como base, não a partir da worktree de backup. A worktree
`codex/control-plane-redesign` continua relevante só como evidência histórica,
não como fonte primária mais nova que a raiz ativa.

## Atualização validada em 2026-07-27 — classificação do overlay local do runtime ativo

### Arquivos tracked modificados classificados

#### Operacionais obrigatórios para o cutover

- `config/project-aliases.yaml`
- `core/knowledge/claude_mem_bridge.py`
- `core/projects/audit.py`
- `npm/lib/supervisor.js`
- `plugins/sqlite-vec-worker/worker.py`
- `scripts/capture/capture-realtime.py`
- `scripts/capture/parsers/antigravity.py`
- `scripts/services/claude-mem-local.ps1`
- `scripts/setup/apply-hidden-supervisor-task.ps1`
- `scripts/setup/register-windows-runtime.ps1`
- `scripts/setup/start-windows-supervisor.ps1`
- `scripts/setup/sync-claude-mem-provider.py`
- `src/hive_mind/capture/identity_store.py`
- `src/hive_mind/capture/ingest.py`
- `src/hive_mind/cli.py`
- `src/hive_mind/validation/canary.py`
- `src/hive_mind/validation/delivery.py`

#### Testes que validam o overlay operacional

- `tests/unit/test_antigravity_parser.py`
- `tests/unit/test_capture_identity_store.py`
- `tests/unit/test_capture_ingest_records_identity.py`
- `tests/unit/test_capture_realtime.py`
- `tests/unit/test_claude_mem_bridge.py`
- `tests/unit/test_projects_audit.py`
- `tests/unit/test_sqlite_vec_worker.py`
- `tests/unit/test_sync_claude_mem_provider.py`
- `tests/unit/test_validation_canary.py`
- `tests/unit/test_windows_install_contract.py`

### Arquivos untracked classificados

#### Operacionais

- `scripts/maintenance/backup.py`
  - wrapper canônico da task `HiveMind-Backup`
- `scripts/setup/start-windows-supervisor-watchdog.ps1`
  - launcher novo do supervisor no Windows
- `src/hive_mind/maintenance/historical_outbox.py`
  - saneamento controlado já aplicado no host
- `src/hive_mind/maintenance/legacy_migration.py`
  - migração controlada do legado UMC já aplicada no host

#### Relatórios operacionais desta missão

- `reports/live-provider-capture-recovery.md`
- `reports/repository-consolidation.md`
- `reports/repository-consolidation.json`

#### Testes de suporte necessários ao cutover

- `tests/unit/test_backup_wrapper.py`
- `tests/unit/test_claude_mem_bridge_recent_first.py`
- `tests/unit/test_historical_outbox.py`
- `tests/unit/test_legacy_migration.py`
- `tests/unit/test_legacy_umc_migration.py`

#### Ainda sem classificação operacional

- `.cursor/rules/hive-mind.md`
- `integrations/integrations.zip`
- `scripts/release/__init__.py`
- `specs/control-plane-redesign.md`

### Leitura técnica do overlay

O overlay local hoje se divide em três blocos:

1. **runtime/capture/identity**
   - supervisor, provider discovery, bridge, ingest, identity store, validação;
2. **manutenção controlada do legado**
   - archival do outbox histórico e migração segura do UMC legado;
3. **prova operacional**
   - testes unitários e relatórios que sustentam o cutover.

Isso confirma que a consolidação canônica não pode ser feita só por branch
history; ela precisa incorporar explicitamente o estado atual da working tree
ativa.

### Blockers operacionais que permanecem ligados a esse overlay

Enquanto este overlay não for consolidado e instalado de forma única, seguem
abertos os blockers já observados no host:

- dual bootstrap do supervisor (`HiveMind-Supervisor` legado + watchdog novo);
- duplicidade `.venv` vs `uv` para processos equivalentes;
- alias/configuração ainda apontando para worktree de backup;
- worktrees e snapshots ainda registradas no caminho operacional.

## Atualização validada em 2026-07-27 — remoção de referência operacional do registry e estado real das tasks

### Correção aplicada no código

O registry canônico de `hive-mind` foi corrigido para remover a worktree de
backup da lista de `roots`. A definição embarcada agora mantém:

- `roots = ['D:\Hive-Mind']`

e preserva somente os aliases históricos de label, sem promover a worktree de
backup como raiz operacional.

Teste adicionado/ajustado:

- `tests/unit/test_projects_audit.py`
  - `test_shipped_hive_mind_registry_root_does_not_point_to_backup_worktrees`

Validação:

- `pytest tests/unit/test_projects_audit.py tests/unit/test_windows_install_contract.py -q`
  - `29 passed`

### Aplicação no host da definição canônica de runtime Windows

Comando executado:

- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:\Hive-Mind\scripts\setup\register-windows-runtime.ps1 -Root D:\Hive-Mind`

Resultado real no host:

- `HiveMind-Supervisor` continua protegido e divergente;
- o script não conseguiu sobrescrevê-lo;
- como fallback controlado, instalou:
  - `C:\Users\miche\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\HiveMind-Supervisor-Watchdog.cmd`

Conteúdo do fallback instalado:

- chama `start-windows-supervisor-watchdog.ps1`
- usa `-Root "D:\Hive-Mind"`
- roda em modo `-Continuous`

### Estado atual das tasks após a tentativa de convergência

| Task / launcher | Estado observado |
|---|---|
| `HiveMind-Supervisor` | ainda legado: `wscript.exe ... start-windows-supervisor-hidden.vbs` |
| `HiveMind-Supervisor-Watchdog` | canônico: `powershell.exe ... start-windows-supervisor-watchdog.ps1 -Root "D:\Hive-Mind"` |
| Startup fallback | instalado e apontando para `D:\Hive-Mind` |

### Leitura operacional após esta etapa

Houve avanço real:

- a referência por **path operacional** para `D:\Hive-Mind\backups\worktrees\...`
  saiu do registry canônico;
- a convergência de bootstrap agora tem um fallback explícito e canônico para
  `D:\Hive-Mind`.

O que ainda resta:

- a task protegida `HiveMind-Supervisor` continua divergente;
- ainda coexistem o launcher legado por `wscript.exe` e o watchdog canônico;
- isso mantém o blocker de dual bootstrap aberto no host.

## Atualização validada em 2026-07-27 — redução da duplicidade operacional real

### Medição após saneamento do watcher órfão

Nova leitura dos processos mostrou:

- **um** `supervisor.js __daemon` ativo:
  - PID `41960`
- **uma** árvore canônica de `sinapse-capture-realtime`:
  - root `.venv`: PID `41912`
  - child `uv` esperado: PID `38732`
- **uma** árvore canônica de `sinapse-api`:
  - root `.venv`: PID `39744`
  - child `uv` esperado: PID `20012`
- **uma** árvore canônica de `sinapse-mcp-http`:
  - root `.venv`: PID `39404`
  - child `uv` esperado: PID `39100`
- **um** watcher Graphify controlado pelo supervisor:
  - `powershell start-watcher.ps1`: PID `48236`
  - `python -m graphify watch`: PID `51184`
  - child `uv` esperado: PID `25896`

### Ação executada

O watcher Graphify duplicado fora do supervisor foi identificado como órfão:

- root órfão: PID `7716`
- child `uv`: PID `13972`

Foi removido com:

- `Stop-Process -Id 7716 -Force`

Resultado:

- watcher órfão extra removido com sucesso;
- o watcher canônico supervisionado permaneceu saudável;
- `logs/supervisor/state.json` continuou marcando `sinapse-graphify-watch = healthy`.

### Leitura técnica atual

Neste snapshot, o dual bootstrap continua existindo **como configuração** no
host, mas a duplicidade operacional mensurável caiu:

- não há múltiplos supervisores ativos;
- não há múltiplas árvores de `capture/api/mcp-http`;
- a duplicidade real remanescente mais sensível agora é a coexistência entre:
  - task legada `HiveMind-Supervisor`
  - watchdog canônico de Startup / Scheduled Task

Ou seja: o blocker já não é “runtime inteiro duplicado”, e sim
**convergência definitiva do dono do bootstrap**.

## Atualização validada em 2026-07-27 — bridge/UMC após reload do runtime

### Gargalo real confirmado

O problema que ainda restava já não era provider nem parser.

Fatos confirmados no host:

- o `setup-brain.bat` continua correto e não foi a causa;
- o `capture-identities.db` e o `hive_mind.db` usados pelo bridge/runtime são os corretos;
- o bridge em lote de `core/knowledge/claude_mem_bridge.py` ainda priorizava linhas antigas (`ORDER BY ... ASC`) com `limit=1000`;
- com backlog grande, sessões recentes podiam permanecer em `POSTED` mesmo já existindo no `claude-mem.db`.

### Correções desta etapa

Arquivos alterados:

- `core/knowledge/claude_mem_bridge.py`
- `src/hive_mind/capture/ingest.py`
- `tests/unit/test_claude_mem_bridge_recent_first.py`
- `tests/unit/test_capture_ingest_records_identity.py`

Comportamento novo:

- o bridge em lote agora prioriza registros mais recentes quando roda com `limit`;
- o `ingest` faz bridge imediato da sessão recém-postada para o UMC;
- quando o bridge imediato confirma `inserted` ou `skipped`, o próprio `ingest` avança o registry para `OBSERVED/BRIDGED`;
- o helper de bridge imediato espera alguns segundos pelos rows reais do worker antes de desistir.

### Evidência operacional medida após restart

Supervisor reiniciado no host:

- `node D:\Hive-Mind\npm\bin\hive-mind.js services restart`
  - `supervisor stopped (pid 29984)`
  - `supervisor started (pid 37564)`

Validação real após reload:

- `hive-mind validate agents --only antigravity --json`
  - `PASSED`

Estado agregado do UMC depois do reload + bridge real:

- `observations = 1285`
- `canonical = 173`
- `legacy = 1112`

Sessões reais que migraram para `BRIDGED` nesta etapa:

- `1341377d-bde9-48ea-bb10-759e995d85e2`
- `078bff54-b4c4-45c2-84e9-1cdb61531255`
- `302222c0-760e-43b4-9dc5-bdef51932964`
- `c0f16988-a618-41b3-8b3a-b41cbe4fa37a`

Exceção remanescente isolada:

- `410bf55f-f785-4798-9095-d37a44876ff1`
  - existe em `sdk_sessions`;
  - continua `POSTED` no `capture-identities.db`;
  - no momento da verificação ainda não tinha `observations/session_summaries` materializados para o `memory_session_id` correspondente;
  - portanto não é mais um problema de identity/path, e sim ausência de payload bridgeável para essa sessão específica.

### Validação executada

- `pytest tests/unit/test_claude_mem_bridge_recent_first.py tests/unit/test_capture_ingest_records_identity.py -q`
  - resultado: `15 passed`
- `python scripts/services/claude_mem_bridge.py`
  - resultado: `inserted = 703`, `scanned = 1000`, `skipped = 297`

## Atualização validada em 2026-07-27 — captura/análises Claude Mem

### Cadeia real do provider continua saindo do setup-brain

Revisão cruzada confirmou que a entrada correta para restaurar o provider continua sendo:

- `D:\Hive-Mind\setup-brain.bat`
- `D:\Hive-Mind\scripts\setup\setup-brain.bat`
- `D:\Hive-Mind\scripts\setup\setup-brain.ps1`
- `D:\Hive-Mind\scripts\setup\setup-brain.py`
- `D:\Hive-Mind\scripts\setup\sync-claude-mem-provider.py`

Conclusão validada no host:

- o papel `HIVE_CLAUDE_MEM_PROVIDER=ollama-cloud` não aparece literalmente no worker;
- ele é traduzido para o slot OpenAI-compatible do Claude Mem;
- o worker ativo ficou coerente com:
  - `CLAUDE_MEM_PROVIDER=openrouter`
  - `CLAUDE_MEM_OPENROUTER_MODEL=gpt-oss:20b`
  - `CLAUDE_MEM_OPENROUTER_BASE_URL=https://ollama.com/v1`

### Causa raiz confirmada do `Unclassified (...)` persistente

O problema restante já não estava no parser isoladamente.

Estado observado e confirmado:

1. o parser do Antigravity já extraía `cwd`/`official_workspace` corretamente de sessões reais;
2. algumas sessões antigas já existentes no `capture-identities.db` permaneciam salvas como `unclassified/antigravity`;
3. ao reaparecer a mesma `content_session_id` com evidência melhor, o registro antigo gerava `identity conflict on the same content_session_id`;
4. no Claude Mem local, `sdk_sessions.project` também podia permanecer preso em `Unclassified (...)` quando a sessão antiga era reaproveitada.

### Correções implementadas e validadas

Arquivos corrigidos:

- `src/hive_mind/capture/identity_store.py`
- `src/hive_mind/capture/ingest.py`
- `scripts/setup/sync-claude-mem-provider.py`
- `C:\Users\miche\.claude\plugins\cache\thedotmack\claude-mem\13.12.4\sqlite\SessionStore.js`

Comportamento novo:

- replay com identidade canônica agora substitui fallback antigo `unclassified/*` no `capture-identities.db`;
- o pós-ingest sincroniza `sdk_sessions.project` no `claude-mem.db` quando a identidade canônica já é conhecida;
- o startup de sync reaplica o patch do `SessionStore.js` e o self-heal do schema de `session_summaries`.

### Evidência real validada no host

Sessão real revalidada:

- `content_session_id = 5ae98e82-8943-44d9-aacc-08ff185a7911`

Estado final confirmado em `D:\Hive-Mind\.hive-mind\state\capture-identities.db`:

- `project_id = local/75a99723f2d2`
- `project_name = Raju Trader`
- `delivery_state = POSTED`

Estado final confirmado em `C:\Users\miche\.claude-mem\claude-mem.db`:

- `sdk_sessions.project = Raju Trader`
- `platform_source = antigravity`
- `obs_count = 1`
- `sum_count = 1`

Estado final confirmado em `D:\Hive-Mind\hive_mind.db`:

- observação bridgeada canônica:
  - `source_id = claude-mem:observations:10101`
  - `workspace_id = local/75a99723f2d2`
- summary bridgeada canônica:
  - `source_id = claude-mem:session_summaries:1071`
  - `workspace_id = local/75a99723f2d2`

### Validação executada

- `pytest tests/unit/test_capture_identity_store.py tests/unit/test_capture_ingest_records_identity.py tests/unit/test_sync_claude_mem_provider.py -q`
  - resultado: `49 passed`
- `hive-mind validate agents --only antigravity --json`
  - resultado: `PASSED`

### Limite conhecido que continua legado

O backlog histórico antigo ainda existe:

- `C:\Users\miche\.claude-mem\capture.db`
- `hive_mind.db` continua majoritariamente com histórico legado `workspace_id=default`

Isso não bloqueia mais o fluxo novo validado acima; as entradas novas dessa sessão já entram com identidade e workspace canônicos.

## Escopo ativo

Fonte de verdade desta fase: instruções do arquivo anexado `pasted-text-1.txt`, que revogam a proibição anterior de atualizar a raiz e priorizam:

- consolidar o projeto numa única raiz canônica;
- atualizar o runtime real `D:\Hive-Mind`;
- eliminar referências operacionais a `backups/worktrees`;
- restaurar e validar a captura dos providers no runtime consolidado.

## Fase 0 — estado real observado no host

### Git — runtime ativo

| Campo | Valor |
|---|---|
| Root | `D:\Hive-Mind` |
| Branch | `codex/universal-provider-capture` |
| HEAD | `52a8441b3b661c15a9385a98d042f2e3c70d0277` |

Arquivos alterados observados:

- `plugins/sqlite-vec-worker/worker.py`
- `scripts/capture/capture-realtime.py`
- `scripts/setup/apply-hidden-supervisor-task.ps1`
- `scripts/setup/register-windows-runtime.ps1`
- `scripts/setup/sync-claude-mem-provider.py`
- `src/hive_mind/capture/identity_store.py`
- `tests/unit/test_capture_identity_store.py`
- `tests/unit/test_capture_realtime.py`
- `tests/unit/test_sqlite_vec_worker.py`
- `tests/unit/test_sync_claude_mem_provider.py`
- `tests/unit/test_windows_install_contract.py`

Untracked relevantes observados:

- `.cursor/rules/hive-mind.md`
- `integrations/integrations.zip`
- `scripts/maintenance/backup.py`
- `scripts/release/__init__.py`
- `scripts/setup/start-windows-supervisor-watchdog.ps1`
- `specs/control-plane-redesign.md`
- `tests/unit/test_backup_wrapper.py`

### Git — worktree de desenvolvimento indicada no anexo

| Campo | Valor |
|---|---|
| Root | `D:\Hive-Mind\backups\worktrees\hive-mind-windows-zero-install` |
| Branch | `codex/control-plane-redesign` |
| HEAD | `315befe40856f476734440a5bf3819bc47e993b4` |

### Worktrees registradas atualmente

| Worktree | Branch | HEAD | Observação |
|---|---|---|---|
| `D:\Hive-Mind` | `codex/universal-provider-capture` | `52a8441b3b661c15a9385a98d042f2e3c70d0277` | runtime ativo |
| `C:\Users\miche\.codex\visualizations\2026\07\13\019f5c0b-88c3-7262-81d3-1e7f24aa69d5\hive-mind-windows-zero-install` | `codex/windows-zero-install` | `aa9435ed1da1bca3fd1de234c3270a37cf471d9e` | worktree externa |
| `C:\Users\miche\.gemini\antigravity\worktrees\Hive-Mind\hive-mind-windows-install` | `hive-mind-windows-install` | `9bc6524be5a383de99313e9bc025f25a4cfb956f` | marcada como `prunable gitdir file points to non-existent location` |
| `D:\Hive-Mind\.tmp\capture-3way-test` | detached | `c2df042c62cd584c85297ad4c8552e969363028e` | temporária |
| `D:\Hive-Mind\backups\worktrees\hive-mind-windows-zero-install` | `codex/control-plane-redesign` | `315befe40856f476734440a5bf3819bc47e993b4` | alvo explícito da consolidação |
| `D:\Hive-Mind-Consolidation\20260722-201726\repo` | `codex/runtime-consolidation` | `c4366aea6c962e28d3370d30350f3b5e79697e9f` | integração anterior |
| `D:\Hive-Mind-Dev\runtime-consolidation-final` | `codex/runtime-consolidation-final` | `52a8441b3b661c15a9385a98d042f2e3c70d0277` | cópia de dev |

### Classificação dirigida das cópias já verificadas

| Path | Classificação | Evidência atual |
|---|---|---|
| `D:\Hive-Mind` | `CANONICAL_RUNTIME` | raiz ativa; processos e tasks apontam para ela |
| `D:\Hive-Mind\backups\worktrees\hive-mind-windows-zero-install` | `DEVELOPMENT_WORKTREE` | branch `codex/control-plane-redesign`, limpa, registrada como worktree |
| `D:\Hive-Mind-Consolidation\20260722-201726\repo` | `BACKUP_SNAPSHOT` | repo limpo de integração anterior; não apareceu em processos/tasks ativos |
| `D:\Hive-Mind-Dev\runtime-consolidation-final` | `BACKUP_SNAPSHOT` | repo limpo de dev; não apareceu em processos/tasks ativos |
| `D:\Hive-Mind\.tmp\capture-3way-test` | `STALE_WORKTREE` | worktree temporária detached com `DirtyLines=21` dentro de `.tmp` |
| `C:\Users\miche\.codex\visualizations\2026\07\13\019f5c0b-88c3-7262-81d3-1e7f24aa69d5\hive-mind-windows-zero-install` | `UNTRACKED_COPY` | worktree externa limpa fora da raiz operacional |
| `C:\Users\miche\.gemini\antigravity\worktrees\Hive-Mind\hive-mind-windows-install` | `STALE_WORKTREE` | `git worktree list` marcou `prunable`, e o path já não existe no disco |

## Fase 1 — preservação externa já executada

Diretório de preservação criado fora da raiz operacional:

- `D:\Hive-Mind-Archive\20260727-141434`

Artefatos já preservados:

- `hive-mind-all-refs.bundle`
- `git_branch_avv.txt`
- `git_tags.txt`
- `git_worktree_list.txt`
- `git_log_all_graph.txt`
- `git_diff_binary.txt`
- `git_diff_cached_binary.txt`
- `git_status_full.txt`
- `git_status_dev_worktree.txt`
- `git_log_lr_runtime_vs_dev.txt`
- `git_diff_stat_runtime_vs_dev.txt`
- `git_diff_name_status_runtime_vs_dev.txt`
- `versions.json`
- `config-hashes.json`
- `process-manifest.json`
- `untracked-manifest.json`
- `scheduled-tasks/*.xml`

Versões registradas no archive:

| Componente | Versão |
|---|---|
| Python do projeto | `3.12.13` |
| Node | `v24.18.0` |
| Bun | `1.3.14` |
| hive-mind | `3.10.1` |

Hashes de configuração registrados sem imprimir segredos:

| Arquivo | SHA-256 |
|---|---|
| `D:\Hive-Mind\.env` | `eea2d8a5e1c7e684c27ecf462cbe080e0d03ac45eba800bbabe5aa7831d4a5aa` |
| `D:\Hive-Mind\config\runtime.yaml` | `a14e348bab25a2d42e69a290e1c5872c229df9590a7e6b8c04f7ec5270f1c31d` |
| `D:\Hive-Mind\config\project-aliases.yaml` | `ca480d58345f10ce36f02b9a1576ddf37f0e56b9c0d6819e2b487e14070df280` |
| `D:\Hive-Mind\config\model-gateway.yaml` | `f2b1310639f289bc03cc2715c8082d65aa81bb901f1bc6c5da9e811da6fffafc` |

## Processos operacionais observados

### Achados críticos imediatos

1. Há dois `supervisor.js` ativos ao mesmo tempo:
   - PID `1520`
   - PID `2068`
2. Há duas instâncias de `capture-realtime.py` ativas ao mesmo tempo:
   - cadeia `19448 -> 23556`
   - cadeia `12056 -> 13316`
3. O runtime ativo está carregando componentes de `D:\Hive-Mind`, mas a orquestração ainda está duplicada no host.
4. O Claude Mem local ativo observado nesta amostra ainda sai do cache em `C:\Users\miche\.claude\plugins\cache\thedotmack\claude-mem\13.6.2`, enquanto MCPs de Claude Mem também aparecem por `C:\Users\miche\.codex\plugins\cache\claude-mem-local\claude-mem\13.12.4`.

### Tabela inicial de componentes observados

| Componente | PID | Command line | Working root inferida |
|---|---:|---|---|
| supervisor Node | 1520 | `node.exe D:\Hive-Mind\npm\lib\supervisor.js __daemon` | `D:\Hive-Mind` |
| supervisor Node | 2068 | `node.exe D:\Hive-Mind\npm\lib\supervisor.js __daemon` | `D:\Hive-Mind` |
| MCP stdio | 9156 / 12304 | `python.exe D:/Hive-Mind/scripts/services/sinapse-mcp.py` | `D:\Hive-Mind` |
| Claude Mem launcher | 22508 | `powershell.exe ... D:\Hive-Mind\scripts\services\claude-mem-local.ps1` | `D:\Hive-Mind` |
| Claude Mem worker wrapper | 9932 | `bun.exe ... worker-wrapper.cjs` | cache Claude |
| Claude Mem worker service | 15792 | `bun.exe ... worker-service.cjs` | cache Claude |
| API | 23800 / 22848 | `python.exe D:\Hive-Mind\scripts\services\sinapse-api.py` | `D:\Hive-Mind` |
| MCP HTTP | 24248 / 22460 | `python.exe D:\Hive-Mind\scripts\services\sinapse-mcp-http.py` | `D:\Hive-Mind` |
| capture-realtime | 19448 / 23556 | `python.exe D:\Hive-Mind\scripts\capture\capture-realtime.py` | `D:\Hive-Mind` |
| capture-realtime | 12056 / 13316 | `python.exe D:\Hive-Mind\scripts\capture\capture-realtime.py` | `D:\Hive-Mind` |

## Tarefas agendadas Hive-Mind observadas

| Task | Action |
|---|---|
| `HiveMind-Backup` | `D:\Hive-Mind\.venv\Scripts\hive-mind.exe backup run --apply` |
| `HiveMind-ClaudeMemBridge` | `D:\Hive-Mind\.venv\Scripts\python.exe "D:\Hive-Mind\scripts\services\claude_mem_bridge.py"` |
| `HiveMind-DreamCycle` | `D:\Hive-Mind\.venv\Scripts\python.exe "D:\Hive-Mind\scripts\dream\dream_cycle.py"` |
| `HiveMind-KnowledgeHealth` | `D:\Hive-Mind\.venv\Scripts\python.exe "D:\Hive-Mind\scripts\health\audit_memory.py"` |
| `HiveMind-PostRebootValidation` | `D:\Hive-Mind\.venv\Scripts\python.exe "D:\Hive-Mind\scripts\health\validate_after_reboot_windows.py"` |
| `HiveMind-Supervisor` | `C:\WINDOWS\System32\wscript.exe "D:\Hive-Mind\scripts\setup\start-windows-supervisor-hidden.vbs" "D:\Hive-Mind"` |
| `HiveMind-Supervisor-Watchdog` | `powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "D:\Hive-Mind\scripts\setup\start-windows-supervisor-watchdog.ps1" -Root "D:\Hive-Mind"` |

### Achado crítico de task

A task instalada `HiveMind-Supervisor` ainda aponta para o launcher antigo `start-windows-supervisor-hidden.vbs`, embora o código local já tenha sido alterado para uma estratégia com watchdog e reinício explícito. Isso prova divergência entre:

- código presente no repo;
- configuração operacional efetivamente instalada no host.

### Causa operacional provável da duplicação observada

Os launchers atuais mostram a seguinte relação:

- `start-windows-supervisor-hidden.vbs` chama `start-windows-supervisor.ps1`
- `start-windows-supervisor.ps1` executa `npm\lib\supervisor.js __daemon`
- `start-windows-supervisor-watchdog.ps1` também consegue iniciar `supervisor.js`, inclusive em laço quando usado com `-Continuous`

Como o host observado mantém:

- a task antiga `HiveMind-Supervisor` usando o launcher VBS;
- a task `HiveMind-Supervisor-Watchdog` usando o watchdog novo;

há evidência suficiente para tratar a duplicação observada de `supervisor.js` e `capture-realtime.py` como um efeito plausível de coexistência de duas estratégias de bootstrap do supervisor no mesmo host.

### Atualização aplicada em 27 de julho de 2026

O registrador nativo do Windows foi ajustado para reconhecer a task protegida
`HiveMind-Supervisor` como compatível quando ela usa:

- `wscript.exe`
- `start-windows-supervisor-hidden.vbs`
- a mesma raiz canônica `D:\Hive-Mind`

Como esse wrapper apenas encadeia
`scripts\setup\start-windows-supervisor.ps1` na mesma raiz, ele não é mais
tratado como divergência operacional material.

Resultado validado no host:

- `HiveMind-Supervisor` continua protegido e não regravável in-place;
- `HiveMind-Supervisor-Watchdog` continua canônico;
- o fallback redundante em Startup
  `HiveMind-Supervisor-Watchdog.cmd` foi removido com sucesso;
- o bootstrap ficou menos redundante sem depender de sobrescrever a task
  protegida.

### Matriz atual de providers comprovados no host canônico

Revalidação em 27 de julho de 2026 com:

- `D:\Hive-Mind\.venv\Scripts\python.exe -m hive_mind.cli validate agents --json`

Providers com fonte real encontrada e prova de ingestão nesta data:

- `antigravity`
- `codex`
- `copilot`
- `hermes`
- `kilo`
- `kimi`
- `mimo`
- `qwen`

Providers sem fonte real comprovada no host nesta data:

- `openclaw`
  - existe `C:\Users\miche\.openclaw`, mas não há `tasks\runs.sqlite`
- `roo`
  - não há `ui_messages.json` nas localizações reais esperadas
- `screenpipe`
  - adapter `timer/REST`; nenhuma fonte viva foi comprovada
- `swarmclaw`
  - não há `data\swarmclaw.db`

Conclusão operacional dessa matriz:

- esses quatro providers não devem ser reportados como `WORKING`;
- hoje o estado correto é `não comprovado no host atual por ausência de fonte real`.

### Validação pós-reboot do runtime ativo

Execução validada em 27 de julho de 2026:

- `D:\Hive-Mind\.venv\Scripts\python.exe D:\Hive-Mind\scripts\health\validate_after_reboot_windows.py`

Resultado observado em `logs/post-reboot-validation.json`:

- `status = pass`
- `profile = local-full`
- `canonical_runtime_paths = true`
- `services_healthy = true`
- `unhealthy_required_services = []`

Implicação:

- no estado real atual do host, o runtime ativo em `D:\Hive-Mind` já passa o
  gate de pós-reboot previsto pelo próprio projeto;
- não há, nesta amostra, referência operacional restante para roots
  não canônicas do Hive-Mind.

### Observação validada — subprocessos `uv` são o comportamento normal desta `.venv`

Foi feito um teste controlado no host executando um script temporário com:

- `D:\Hive-Mind\.venv\Scripts\python.exe`

Resultado observado:

- o launcher da `.venv` sobe como processo pai;
- o interpretador real filho aparece como:
  - `C:\Users\miche\AppData\Roaming\uv\python\cpython-3.12-windows-x86_64-none\python.exe`

O `pyvenv.cfg` da própria `.venv` confirma:

- `home = C:\Users\miche\AppData\Roaming\uv\python\cpython-3.12-windows-x86_64-none`

Portanto, neste host, ver filhos apontando para o Python do `uv` **não é evidência suficiente de desvio operacional**. É o comportamento normal do ambiente virtual atual baseado em `uv`.

O critério correto para a consolidação continua sendo:

- processos pais/entrypoints/tarefas/launchers apontarem para `D:\Hive-Mind`
- e não para `backups/worktrees`

Isso remove um falso positivo da investigação e evita um cutover baseado numa premissa errada.

## Referências operacionais ou semicanônicas a worktree/backups encontradas

### Confirmadas em código/configuração do runtime

- `config/project-aliases.yaml` contém alias explícito para `D:\Hive-Mind\backups\worktrees\hive-mind-windows-zero-install`

### Confirmadas como ausentes em processos ativos observados

Na amostra dirigida de processos, não apareceu nenhum `CommandLine` executando diretamente de:

- `D:\Hive-Mind\backups\worktrees\hive-mind-windows-zero-install`
- `C:\Users\miche\.codex\visualizations\2026\07\13\019f5c0b-88c3-7262-81d3-1e7f24aa69d5\hive-mind-windows-zero-install`

### Encontradas em testes/documentação de comportamento

Há múltiplas referências a `hive-mind-windows-zero-install` em testes de identidade e política de path. Essas referências não são necessariamente falhas operacionais; precisam ser classificadas depois em:

- cobertura legítima de regressão;
- política de bloqueio de paths não canônicos;
- ou dependência indevida do caminho antigo.

## Conclusões parciais

1. O host ainda não está em estado canônico único.
2. Há duplicação real de orquestração (`supervisor.js`) e de captura (`capture-realtime.py`).
3. O runtime ativo está em `D:\Hive-Mind`, mas a camada instalada de agendamento ainda não está totalmente alinhada com o código atual do repo.
4. A comparação Git entre `52a8441b3b66...` (runtime ativo) e `315befe40856...` (worktree `codex/control-plane-redesign`) não mostrou commits exclusivos da worktree de desenvolvimento; nessa relação, apenas o runtime ativo aparece à frente.
5. A comparação de arquivos rastreados também mostrou somente arquivos presentes no runtime ativo e ausentes na worktree de desenvolvimento, incluindo:
   - `.github/workflows/p3-fresh-machine.yml`
   - `docs/operations/cutover-owner-contract.md`
   - `docs/superpowers/plans/2026-07-22-runtime-consolidation.md`
   - `reports/staging-gate.md`
   - `scripts/health/audit_runtime_paths_windows.py`
   - `src/hive_mind/validation/runtime_paths.py`
   - `tests/integration/test_copilot_parser_identity.py`
   - `tests/unit/test_cutover_owner_contract.py`
   - `tests/unit/test_ragflow_minio_contract.py`
   - `tests/unit/test_runtime_path_policy.py`
   - `tests/unit/test_vault_legacy_encoding.py`
   - `tests/unit/test_windows_backup_task_migration.py`
6. A worktree `D:\Hive-Mind\backups\worktrees\hive-mind-windows-zero-install` estava limpa na amostra observada (`git status --short` vazio), o que reduz indício de conteúdo não commitado exclusivo nela.
7. A duplicação operacional observada no host é compatível com coexistência indevida da task antiga `HiveMind-Supervisor` e do watchdog novo.
8. O `supervisor.log` também mostra reinicializações de `sinapse-sqlite-vec`, `sinapse-api` e `sinapse-capture-realtime` após `external degraded ollama: readiness timeout for ollama`, então a estabilidade do runtime ainda depende do comportamento do supervisor diante de falhas transitórias do Ollama.
9. Ainda não há evidência suficiente para declarar zero referências operacionais a worktrees/backups, porque a configuração `config/project-aliases.yaml` ainda materializa o caminho da worktree em backup.

## Correção aplicada nesta etapa

### Bootstrap singleton do supervisor Windows

Foi aplicada uma correção em dois níveis:

## Snapshot desta etapa — 2026-07-27

### Captura realtime e análises do Codex

- A sessão real do Codex `019f8c0c-5534-7131-a3f7-1d7a9c6dd3de` deixou de ficar travada em `QUARANTINED`.
- Evidência atual em `D:\Hive-Mind\.hive-mind\state\capture-identities.db`:
  - `delivery_state = POSTED`
  - `last_error = NULL`
- Evidência atual em `C:\Users\miche\.claude-mem\claude-mem.db` para a mesma sessão:
  - `memory_session_id = openrouter-019f8c0c-5534-7131-a3f7-1d7a9c6dd3de-1785172305849`
  - `93` observações
  - múltiplos `session_summaries` recentes (`id` 979–983)

### Correções de código aplicadas

- `src/hive_mind/capture/identity_store.py`
  - replay com a mesma identidade após quarentena por conflito volta para `PENDING` em vez de permanecer travado para sempre
- `scripts/capture/capture-realtime.py`
  - conflitos de identidade passam a ser logados explicitamente
- `src/hive_mind/validation/canary.py`
  - backlog histórico de `C:\Users\miche\.claude-mem\capture.db` deixa de reprovar providers do caminho realtime atual
  - `default_fresh_marker_paths()` agora prefere o banco real `capture-identities.db`

### Validação executada

- Testes:
  - `pytest tests/unit/test_capture_identity_store.py tests/unit/test_validation_canary.py -q`
  - resultado: `60 passed`
- Validação real do host:
  - `hive-mind validate agents --json`
  - resultado atual:
    - `PASSED`: `codex`, `copilot`, `hermes`, `kilo`, `kimi`, `mimo`, `qwen`
    - `FAILED`: `antigravity`
    - `SKIPPED`: `openclaw`, `roo`, `screenpipe`, `swarmclaw`

### Pendente após esta etapa

- O `setup-brain.bat` não foi alterado nesta etapa; a correção aplicada ficou no runtime de captura/validação, preservando a configuração atual de providers.

## Snapshot adicional — correção do Antigravity

### Defeito confirmado

- O parser de `scripts/capture/parsers/antigravity.py` entregava sessões CLI reais sem `cwd` nem `official_workspace`.
- Com isso, o `ProjectIdentityResolver` recebia apenas:
  - `provider = antigravity`
  - `surface = cli`
  - sem raiz de workspace
- Resultado observado antes da correção:
  - `project_id = unclassified/antigravity`
  - `resolution_method = unclassified_provider`

### Evidência real usada para a correção

Sessão real inspecionada:

- `C:\Users\miche\.gemini\antigravity-cli\conversations\e64ecfcd-7a45-4b28-981a-73663d272247.db`

Nos `step_payload` desta sessão existem paths reais do workspace, por exemplo:

- `AbsolutePath = D:/Raju Trader/Docs/impement/00-agent-bible.md`
- `DirectoryPath = D:/Raju Trader`
- `Cwd = D:/Raju Trader`

### Correção aplicada

- `scripts/capture/parsers/antigravity.py`
  - extrai `Cwd`, `DirectoryPath`, `SearchPath` e `AbsolutePath` dos payloads do banco CLI
  - promove essa evidência para `cwd` e `official_workspace`
- `tests/unit/test_antigravity_parser.py`
  - agora prende a preservação de `cwd`/`official_workspace` no parser CLI

### Validação após a correção

- Testes:
  - `pytest tests/unit/test_antigravity_parser.py tests/unit/test_provider_parser_identity_contract.py -q`
  - resultado: `38 passed`
- Verificação direta da sessão real:
  - `cwd = D:\Raju Trader\Docs\impement`
  - `official_workspace = D:\Raju Trader\Docs\impement`
  - `project_id = local/75a99723f2d2`
  - `repository_root = D:\Raju Trader`
  - `resolution_method = official_workspace`
- Validação do provider:
  - `hive-mind validate agents --only antigravity --json`
  - resultado: `PASSED`

### Runtime carregado com o parser novo

- `sinapse-capture-realtime` foi reiniciado pelo supervisor
- evidência em `logs/supervisor/supervisor.log`:
  - `2026-07-27T17:39:49.939Z exit sinapse-capture-realtime code=4294967295 — restart in 15000ms`
  - `2026-07-27T17:40:04.960Z start sinapse-capture-realtime pid=1892`
  - `2026-07-27T17:40:04.960Z ready sinapse-capture-realtime pid=1892`

### Estado geral do host após esta etapa

- `hive-mind validate agents --json`
- resultado:
  - `PASSED`: `antigravity`, `codex`, `copilot`, `hermes`, `kilo`, `kimi`, `mimo`, `qwen`
  - `SKIPPED`: `openclaw`, `roo`, `screenpipe`, `swarmclaw`
  - `FAILED`: nenhum

1. `scripts/setup/start-windows-supervisor.ps1`
   - antes chamava `supervisor.js __daemon` diretamente;
   - agora chama `require(...).start()`, passando pelo guard oficial do supervisor.

2. `npm/lib/supervisor.js`
   - adicionado lock de bootstrap em `logs/supervisor/supervisor.start.lock`;
   - o `start()` agora serializa partidas concorrentes e retorna cedo com
     `supervisor start already in progress` quando outro bootstrap já está em curso.

### Validação

- teste de contrato Windows:
  - `tests/unit/test_windows_install_contract.py`
  - resultado: `19 passed`
- estado do host após limpeza manual das instâncias antigas e novo bootstrap:
  - `supervisor.pid = 11256`
  - uma única instância `node.exe ... supervisor.js __daemon` observada
  - `sinapse-capture-realtime` voltou a `healthy` no `state.json`
  - `sinapse-api`, `sinapse-mcp-http` e `sinapse-sqlite-vec` também ficaram `healthy`

### Estado residual após a correção

O runtime ainda não está verde completo porque:

- `ollama` permanece `degraded`
- `syncthing-watcher` ainda não estabilizou

Isso significa que a correção desta etapa resolveu o bootstrap duplicado do supervisor, mas não encerra a investigação da instabilidade do runtime completo.

## Correção aplicada nesta etapa — registrador do runtime Windows

### Problema confirmado

O script canônico de alinhamento do host `scripts/setup/register-windows-runtime.ps1`
estava incompatível com o PowerShell real do host por usar o operador `??`.
Isso quebrava o caminho que deveria convergir as Scheduled Tasks para o contrato
canônico do repo.

Além disso, mesmo quando a task protegida antiga `HiveMind-Supervisor` existia
com ação divergente (launcher VBS legado), o script apenas avisava e aceitava o
desvio, sem instalar nenhum fallback.

### Correção aplicada

1. `scripts/setup/register-windows-runtime.ps1`
   - removido o uso de `??`, substituído por lógica compatível com Windows
     PowerShell;
   - adicionadas funções para comparar a ação instalada com a ação planejada;
   - quando `HiveMind-Supervisor` ou `HiveMind-Supervisor-Watchdog` estiverem
     protegidas **e divergirem do contrato canônico**, o script agora instala o
     fallback de Startup em vez de aceitar o desvio silenciosamente.

2. `tests/unit/test_windows_install_contract.py`
   - atualizado para verificar o novo critério de ownership canônico do
     scheduler;
   - adicionado teste de contrato para o caso de task protegida e divergente.

### Validação

- `pytest tests/unit/test_windows_install_contract.py tests/unit/test_sync_claude_mem_provider.py -q`
  - resultado: `24 passed`

- execução real do registrador:
  - comando: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\setup\register-windows-runtime.ps1 -Root D:\Hive-Mind`
  - resultado observado:
    - `HiveMind-Supervisor is protected and diverges from the canonical action; installing Startup watchdog fallback.`
    - fallback instalado em:
      - `C:\Users\miche\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\HiveMind-Supervisor-Watchdog.cmd`

- conteúdo validado do fallback instalado:
  - inicia `start-windows-supervisor-watchdog.ps1`
  - usa `-Continuous`
  - aponta para `D:\Hive-Mind`

### Situação operacional após esta etapa

- a Scheduled Task protegida antiga continua instalada:
  - `HiveMind-Supervisor` → `wscript.exe ... start-windows-supervisor-hidden.vbs`
- mas o host agora tem um fallback persistente de Startup que força o bootstrap
  canônico do watchdog mesmo sem permissão para sobrescrever a task antiga.

### Observação importante sobre processos Python

A revalidação do host mostrou que, para serviços como `sinapse-api`,
`sinapse-mcp-http`, `capture-realtime` e `sqlite-vec-worker`, o processo
`C:\Users\miche\AppData\Roaming\uv\python\...` aparece como **filho direto** do
Python da `.venv` de `D:\Hive-Mind`. Portanto, nesta amostra, isso não prova
duplicação indevida por si só; pode ser apenas o wrapper normal do ambiente
gerido por `uv`.

## Correção aplicada nesta etapa 2

### Resumos/análises do claude-mem restaurados

Foi confirmada a causa do sintoma relatado pelo usuário ("captura em tempo real aparece, mas análises/resumos não são gerados"):

- o worker do claude-mem estava processando observações normalmente;
- ao tentar persistir `session_summaries`, falhava com:
  - `table session_summaries has no column named discovery_tokens`
- o banco real afetado era:
  - `C:\Users\miche\.claude-mem\claude-mem.db`

### Evidência observada no runtime real

No log do worker global (`~/.claude-mem/logs/claude-mem-2026-07-27.log`) apareceu:

- `STORING ... hasSummary=true`
- seguido por:
  - `OpenRouter message processing failed ... table session_summaries has no column named discovery_tokens`
  - `FTS5 fallback search failed no such column: s.discovery_tokens`

Isso prova que:

1. a captura estava chegando ao worker;
2. o modelo estava gerando resposta suficiente para tentar salvar resumo;
3. a quebra ocorria no schema SQLite, não na captura em si.

### Correção operacional aplicada

Foi executado o fluxo oficial do projeto:

- `D:\Hive-Mind\.venv\Scripts\python.exe D:\Hive-Mind\scripts\setup\sync-claude-mem-provider.py`

Resultado observado:

- `OK esquema de resumos atualizado: discovery_tokens, memory_session_id ON UPDATE CASCADE`
- restart do supervisor/worker concluído

### Correção permanente no código

Para não depender de rodar `setup-brain.bat` manualmente após reboot:

1. `scripts/setup/sync-claude-mem-provider.py`
   - ganhou o modo `--ensure-schema-only`
   - faz apenas a autocorreção idempotente do schema do banco global do claude-mem

2. `scripts/services/claude-mem-local.ps1`
   - agora executa essa autocorreção automaticamente antes de subir o worker em `start`/`worker`

3. `tests/unit/test_windows_install_contract.py`
   - recebeu contrato garantindo que o launcher Windows do claude-mem chama a autocura de schema no startup

### Validação

- testes:
  - `pytest tests/unit/test_windows_install_contract.py tests/unit/test_sync_claude_mem_provider.py -q`
  - resultado: `23 passed`
- autocura isolada:
  - `python scripts/setup/sync-claude-mem-provider.py --ensure-schema-only`
  - resultado: `OK esquema de resumos já compatível`
- banco após correção:
  - `session_summaries.discovery_tokens` presente
  - FK `memory_session_id -> sdk_sessions(memory_session_id)` com `ON UPDATE CASCADE`
  - novas linhas de `session_summaries` já consultáveis no banco

### Estado do runtime após a etapa

Em `logs/supervisor/state.json`, após o restart e estabilização:

- `sinapse-claude-mem`: `healthy`
- `sinapse-sqlite-vec`: `healthy`
- `sinapse-api`: `healthy`
- `sinapse-mcp-http`: `healthy`
- `sinapse-capture-realtime`: `healthy`
- `ollama`: `degraded`
- `syncthing-watcher`: `degraded`

Também foi observada coexistência de processos antigos ainda rodando via Python do `uv` em:

- `C:\Users\miche\AppData\Roaming\uv\python\cpython-3.12-windows-x86_64-none\python.exe`

enquanto o runtime atual saudável já usa:

- `D:\Hive-Mind\.venv\Scripts\python.exe`

Isso não foi a causa direta da quebra dos resumos, mas permanece como fonte de instabilidade operacional do host.

## Próximos passos imediatos

1. Comparar `D:\Hive-Mind` versus `D:\Hive-Mind\backups\worktrees\hive-mind-windows-zero-install` por diff e arquivos exclusivos relevantes à consolidação.
2. Exportar manifesto de tarefas/processos/configurações com hashes e paths para arquivo estruturado.
3. Classificar todas as worktrees/cópias encontradas em `CANONICAL_RUNTIME`, `DEVELOPMENT_WORKTREE`, `BACKUP_SNAPSHOT`, `STALE_WORKTREE`, `UNTRACKED_COPY` ou `UNKNOWN`.
4. Corrigir a divergência entre task instalada e launcher canônico somente depois da consolidação do código e validação staging.

## Atualização validada em 2026-07-27 — ACTIVE vs DEVELOPMENT para o cutover

### Relação real entre os dois HEADs

Comparação executada no host real:

- `ACTIVE = 52a8441b3b661c15a9385a98d042f2e3c70d0277`
- `DEVELOPMENT = 315befe40856f476734440a5bf3819bc47e993b4`
- `git merge-base ACTIVE DEVELOPMENT = 315befe40856f476734440a5bf3819bc47e993b4`

Isto prova que, no histórico Git commitado observado agora:

- `DEVELOPMENT` é ancestral direto de `ACTIVE`;
- não há commits exclusivos da worktree `codex/control-plane-redesign` que estejam faltando no runtime ativo;
- a consolidação não é mais um merge entre duas linhas divergentes de commits;
- o risco real migrou para mudanças locais não commitadas e para referências operacionais antigas ainda apontando para `backups/worktrees`.

### Commits exclusivos do runtime ativo após o ponto comum

Commits operacionalmente relevantes presentes em `ACTIVE` e ausentes em `DEVELOPMENT`:

- `349418c` — resolve Windows installer from current checkout
- `0d9869d` — skip empty newest provider sources
- `0f864d2` — enforce canonical operational paths
- `8f325bf` — harden canonical path audit
- `94dde2d` — preserve Copilot workspace identity
- `2833d27` — discover Copilot and Antigravity sources at their real paths
- `4fd3233` — serialise SeenStore access across watcher threads
- `4b11db4` — prove a fresh marker traversed the real capture chain
- `a205d7d` — stop the path audit flagging canonical services
- `9303f4e` — reject canonical `.tmp` and `backups` runtime targets
- `d2a4a44` — close canonical runtime health prerequisites
- `99b586a` / `912dd53` — CI de fresh-machine para validar cutover

Não foram observados commits exclusivos do `DEVELOPMENT` contra esse mesmo ponto comum.

### Áreas com maior risco de conflito no cutover

O risco atual está concentrado em três grupos:

1. código commitado em `ACTIVE` que já redefiniu comportamento canônico de runtime/captura:
   - `scripts/capture/capture-realtime.py`
   - `scripts/capture/capture_adapters.py`
   - `scripts/capture/capture_sources.py`
   - `scripts/capture/parsers/copilot.py`
   - `scripts/capture/parsers/kilo.py`
   - `src/hive_mind/capture/engine.py`
   - `src/hive_mind/cli.py`
   - `src/hive_mind/validation/canary.py`
   - `src/hive_mind/validation/runtime_paths.py`

2. mudanças locais ainda não commitadas no runtime ativo:
   - `config/project-aliases.yaml`
   - `core/knowledge/claude_mem_bridge.py`
   - `core/projects/audit.py`
   - `npm/lib/supervisor.js`
   - `plugins/sqlite-vec-worker/worker.py`
   - `scripts/capture/capture-realtime.py`
   - `scripts/capture/parsers/antigravity.py`
   - `scripts/services/claude-mem-local.ps1`
   - `scripts/setup/register-windows-runtime.ps1`
   - `scripts/setup/start-windows-supervisor.ps1`
   - `src/hive_mind/capture/identity_store.py`
   - `src/hive_mind/capture/ingest.py`
   - `src/hive_mind/cli.py`
   - `src/hive_mind/validation/canary.py`
   - `src/hive_mind/validation/delivery.py`

3. artefatos operacionais novos ainda untracked, mas potencialmente necessários ao cutover:
   - `scripts/setup/start-windows-supervisor-watchdog.ps1`
   - `scripts/maintenance/backup.py`
   - `src/hive_mind/maintenance/legacy_migration.py`
   - `src/hive_mind/maintenance/historical_outbox.py`
   - `reports/live-provider-capture-recovery.md`
   - `reports/repository-consolidation.md`
   - `reports/repository-consolidation.json`

### O que não pode se perder no cutover

Itens do runtime ativo que precisam sobreviver integralmente ao cutover:

- endurecimento de path canônico e bloqueio de runtime em `backups`/`.tmp`;
- descoberta real de fontes Copilot e Antigravity;
- preservação de identidade/workspace do Copilot;
- serialização do `SeenStore` nas threads de captura;
- prova/validação de fresh marker ponta a ponta;
- wrappers e validações Windows ligados ao checkout atual;
- saneamento local já aplicado em bridge, ingest, identity store, supervisor e sqlite-vec worker;
- limpeza controlada já feita no banco operacional:
  - `capture_outbox.total = 0`
  - `legacy.unclassified_legacy = 0`
- preservação explícita do bloco histórico `default/ins`, sem migração forçada.

### Implicação prática

Com a evidência atual, o cutover seguro deve tratar `D:\Hive-Mind` como fonte primária do estado operacional mais recente.

A worktree `D:\Hive-Mind\backups\worktrees\hive-mind-windows-zero-install` continua relevante como ponto histórico/base de desenvolvimento, mas não contém, no estado Git observado hoje, commits mais novos do que o runtime ativo.

## Atualização validada em 2026-07-27 20:30 BRT — bootstrap Windows canônico no host real

Esta atualização substitui a leitura anterior que ainda tratava o fallback de Startup como presente.

### Estado revalidado no host

- `HiveMind-Supervisor`
  - continua protegido
  - `Execute = C:\WINDOWS\System32\wscript.exe`
  - `Arguments = "D:\Hive-Mind\scripts\setup\start-windows-supervisor-hidden.vbs" "D:\Hive-Mind"`
  - `WorkingDirectory = D:\Hive-Mind`
  - leitura: wrapper legado, mas compatível com a raiz canônica
- `HiveMind-Supervisor-Watchdog`
  - `Execute = powershell.exe`
  - `Arguments = -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "D:\Hive-Mind\scripts\setup\start-windows-supervisor-watchdog.ps1" -Root "D:\Hive-Mind"`
  - `WorkingDirectory = D:\Hive-Mind`
  - leitura: task canônica e exata
- Startup fallback
  - `C:\Users\miche\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\HiveMind-Supervisor-Watchdog.cmd`
  - estado atual: ausente

### Reaplicação do registrador

Comando executado no host:

- `powershell -NoProfile -ExecutionPolicy Bypass -File D:\Hive-Mind\scripts\setup\register-windows-runtime.ps1 -Root D:\Hive-Mind`

Saída observada:

- `HiveMind-Supervisor is protected; keeping its existing definition.`
- `HiveMind-PostRebootValidation is protected; keeping its existing definition.`

Não houve reinstalação do fallback de Startup.

### Leitura operacional consolidada

- não há task Hive-Mind apontando para `\backups\`, `\worktrees\` ou `hive-mind-windows-zero-install`;
- o bootstrap Windows ainda é dual como mecanismo de entrada:
  - task legada protegida por `wscript.exe`
  - watchdog canônico por `powershell.exe`
- porém os dois caminhos agora convergem para `D:\Hive-Mind`;
- o fallback redundante em Startup não faz mais parte do caminho operacional;
- o risco residual deixou de ser “duplo bootstrap com fallback extra” e passou a ser apenas “task protegida ainda não regravável in-place”.

### Resultado desta frente

- raiz operacional confirmada: `D:\Hive-Mind`
- zero referências operacionais a backup/worktree nas Scheduled Tasks Hive-Mind revalidadas
- fallback redundante de Startup removido no host
- `supervisor.js __daemon` continua único no topo do runtime observado
