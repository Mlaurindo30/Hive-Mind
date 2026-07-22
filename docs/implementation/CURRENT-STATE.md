# Project Status Dashboard

- **branch:** `codex/control-plane-redesign`
- **HEAD:** `11cd752` — último commit de `git log` no momento em que este
  painel foi escrito. Por construção ele fica atrás do HEAD atual por
  exatamente **um** commit: aquele que grava esta linha, cujo SHA não existe
  antes de existir. O validador aceita esse único passo **só** se o commit
  for somente-documentação, e falha para qualquer commit de código.
- **active delivery:** **SEC-001** — bloqueio humano único: rotação da chave.
  D004-M bloqueada até isso e até uma observation real.
- **last completed delivery:** **D009-R6** (registradores → wrappers).
  D004-R2 e D004-R2W estão **PARTIAL**. Antes dela: D004-R2 (**PARTIAL**, não fechada), D009-R6
  (`adcac3d` −442/−430 linhas, `47912f2`, `20adb39`; wrappers com 32 e 22
  linhas executáveis, zero lógica de produto — evidência verificada) e
  D001-R2 — 6 commits, nesta ordem:
  1. `7b40e59` `docs(implementation): reconcile project status with current HEAD`
  2. `9bd34f4` `docs(implementation): point the dashboard at the reconciliation commit`
  3. `7fc70dd` `docs(implementation): set dashboard HEAD to 9bd34f4`
  4. `18eab01` `test(implementation): anchor the HEAD-rule tests to a synthetic repo`
  5. `d3e4c6d` `docs(implementation): close D001-R2 at 18eab01`
  6. `776d504` `docs(implementation): correct dashboard HEAD, ordering and delivery states`
- **next delivery:** D004-R2 → D002-R1 → D005-R1 → D006-R2/R3 → D008-R2/R3 →
  D011-A → D010-G0 (**não ir de D009-R6 direto a D010-G0**)
- **documentos vs Git:** verificados por `hive-mind implementation validate`.
- **disciplina de fechamento:** atualizar este HEAD é o **último** passo de
  qualquer entrega, num commit que toque apenas `docs/implementation/`.
  Qualquer outra ordem deixa o painel obsoleto no próprio commit que o
  atualiza.
- **native control plane compliance:** PARTIAL
- **runtime active root:** `D:\Hive-Mind` (não alterado, exceto DR-001 autorizado)
- **runtime active owner:** Task Scheduler + `npm/lib/supervisor.js` (legado)
- **D010 status:** **BLOCKED** — exige D010-G0 DONE
- **installation status:** instalação limpa NÃO executada
- **reboot status:** reboot NÃO executado
- **real data migration status:** NÃO executada, e **não será** nesta fase —
  os registros históricos fragmentados permanecem onde estão. O defeito de
  identidade que os criou está corrigido em D004-R2: `project` deixou de
  aceitar rótulo livre, e `project_name` deixou de derivar do basename da
  worktree. Eventos **novos** entram canônicos; o backlog é uma decisão
  separada. Ver a errata e o fechamento no [ledger](DELIVERY-LEDGER.md).
- **last full regression:** `pytest tests/unit` — **1359 passed, 18 skipped,
  2 failed** (D004-R2). As 2 são as conhecidas de
  `test_windows_install_contract.py`, provadas pré-existentes por stash.
- **known test failures (17, todas pré-existentes a D001-R2):**
  - 2 em `test_windows_install_contract.py` — UnicodeDecodeError de stdout PowerShell;
  - 1 em `test_acceptance_split.py` — `test_canary_multiagent_pipeline.py` e
    `test_e2e_memory_to_query_pipeline.py` sem `@pytest.mark.real`;
  - 2 em `tests/model_gateway/` — bridge legado e execução não suportada;
  - 12 em `tests/real/` — exigem backends vivos (Milvus, FalkorDB, modelos)
    e a cadeia de captura, que está quebrada (D004-R2).
- **worktree status:** limpa, exceto 16 untracked em `.tmp/` (LOCAL TEST ARTIFACT)

## Entregas

**Estados oficiais**, e são os únicos: `NOT_STARTED`, `IN_PROGRESS`,
`PARTIAL`, `BLOCKED`, `FAILED`, `DONE`, `SUPERSEDED`.

Um qualificador — dados sintéticos, config temporária, somente leitura — vai
na coluna de evidência, **nunca** na de estado. `DONE_SYNTHETIC` como estado
parecia informativo e não era: escondia um `PARTIAL` atrás de uma palavra que
começa com DONE, e o leitor que só escaneia a coluna via a entrega fechada.

| Delivery | Objective | Status | Last commit | Real proof | Remaining |
|---|---|---|---|---|---|
| D001 | Documentação viva | **DONE** | `834e405` | 8 docs, aprovado | — |
| D002 | Dream Cycle por project_id | **PARTIAL** | `2ae8558` | unit + SQLite real | ciclo real com modelos |
| D003 | Identidade de projeto validada | **PARTIAL** | `fca4c5a` | repo Git real + registry | canário por provider |
| D004 | Canários multiagente | **PARTIAL** | `989ebee` | canário real: 4 pass, 4 fail; identidade canônica corrigida (D004-R2) | matriz por provider |
| D005 | E2E memória → consulta | **PARTIAL** | `d793353` | testes reais | depende de scripts não portados |
| D006 | Manifesto declarativo | **PARTIAL** | `1db2523` | 10 testes | 4 catálogos concorrentes |
| D007 | Daemon shadow | **PARTIAL** | `cb4c66d` | run --shadow real, HTTP, socket | cutover; evidência: código pronto, sem cutover |
| D008 | Supervisor e scheduler | **PARTIAL** | `1857869` | processos sintéticos reais | disparo de jobs, cutover |
| D009 | Registro MCP/captura nativo | **PARTIAL** | `47912f2` | detect 9/13, doctor 1/9 healthy, TOML nativo, wrappers mínimos | captura real **não** provada — gate é D004-R2 |
| D010 | Cutover de owners legados | **BLOCKED** | — | — | exige D010-G0 |
| D011 | Installer e lifecycle Windows | NOT_STARTED | — | — | — |
| D012 | Windows descartável + reboot | NOT_STARTED | — | — | — |
| D013 | Atualização da raiz | NOT_STARTED | — | — | — |
| D014 | Limpeza de shims e release | NOT_STARTED | — | — | — |

### Subentregas de remediação

| ID | Objetivo | Status | Commit | Prova |
|---|---|---|---|---|
| D009-R1 | Auditoria de propriedade nativa | **DONE** | `4223505` | 6 achados (A-01…A-06) |
| D009-R2 | Testes arquiteturais | **DONE** | `a8f0e59` | 14 testes verdes |
| D009-R3 | Paridade POSIX do capture hook | **DONE** | `fef5383` | ADR-004 restaurado |
| D009-R4 | Writer TOML do Codex | **DONE** | `e86b1fa` | cópia do config real (181 L); evidência: configs temporários |
| D009-R5 | doctor, unregister, instruções nativas | **DONE** | `25d348a` | doctor real: 1/9 healthy; captura = TO_REMOVE; evidência: configs temporários |
| D009-R6 | Wrappers PS1/SH mínimos | **DONE** | `47912f2` | 79 testes; PS1 456→55 L, SH 444→50 L; cadeia wrapper→CLI→config em temp; evidência: configs temporários |
| D001-R2 | Reconciliar documentos com a verdade do Git | **DONE** | `776d504` | validador nativo: 11 checks, 18 testes |
| D004-R2 | Identidade canônica na captura | **PARTIAL** | `0664afc` | ingest nativo e identidade canônica implementados; payload de ingestão comprovado até a fronteira do worker; bridge comprovado separadamente contra stores temporárias | matriz por provider |
| D004-R2W | Entrega via worker real isolado | **PARTIAL** | `eb535f5` | 31 testes; worker descartável, ambiente por allowlist, provider **local sem credencial**, **2 observations reais** com `project` canônico | envelope não sobrevive até a observation (M14) |
| **SEC-001** | Credencial de provider exposta na saída | **BLOCKED** | `1cdc7d5` | scanner sem impressão: 0 ocorrências em 14.973 objetos Git, 9.580 arquivos, staged e mensagens | **rotação humana da chave** |
| D004-M | Matriz por provider | **BLOCKED** | — | — | depende de SEC-001 e de uma observation real |
| D010-C1 | Remover propriedade legada do capture hook | **NOT_STARTED** | — | writers e paths de config registrados | depende de D004-M |
| D002-R1 | Dream Cycle operacional sobre project_id real | NOT_STARTED | — | — |
| D005-R1 | E2E real: memória gravada → consultável | NOT_STARTED | — | — |
| D006-R2 | Entrypoints nativos de serviço | NOT_STARTED | — | — |
| D006-R3 | runtime.yaml como catálogo único | NOT_STARTED | — | — |
| D008-R2 | Disparo real de jobs pelo scheduler | NOT_STARTED | — | — |
| D008-R3 | Journal de cutover e rollback | NOT_STARTED | — | — |
| D011-A | Installer nativo (resolve circularidade D010/D011) | NOT_STARTED | — | — |
| D003-R1 | Resolver no pacote nativo | **DONE** | `bf60028` | 115 testes; legado é shim |
| D004-R1 | Canary runner nativo | **DONE** | `e83d260` | canário sobre dados reais |
| D006-R1 | Catálogo único | **PARTIAL** | `b9af988` | bloqueado: 4 serviços aspiracionais + post-reboot ausente |
| D008-R1V | Inventário de jobs validado | **DONE** | `33191e3` | 18 jobs vivos; 1 morto removido |
| D008-R1B | Backup nativo verificado | **PARTIAL** | `4f22a3c` | run→verify→restore sintético; evidência: dados sintéticos |
| DR-001 | Restart policy do Docker | **DONE** | `69632bd` | 7/7 containers `unless-stopped` |
| **D010-G0** | **Windows Native Migration Readiness** | **NOT_STARTED** | — | gate obrigatório de D010: 15 completos / 8 falhando / 1 parcial de 24 |

Inventário completo: [WINDOWS-NATIVE-MIGRATION.md](WINDOWS-NATIVE-MIGRATION.md)

### Este painel é verificável

`hive-mind implementation status` deriva HEAD, branch, contadores do gate e
LEGACY_OWNER das fontes reais; `hive-mind implementation validate` falha se
este documento discordar do repositório. `tests/unit/test_implementation_validation.py`
roda os mesmos checks na regressão, então a divergência aparece como teste
vermelho e não como algo que um leitor precisa notar.
— 15 `LEGACY_OWNER` bloqueiam D010, 0 `UNKNOWN`.

---

# Current Implementation State

> **Auditoria D009-R1 (2026-07-20):** este documento foi revisado contra o
> código. Ver [AUDIT-D001-D009.md](AUDIT-D001-D009.md). Compliance da
> arquitetura nativa: **PARTIAL** — nada de lógica nova entrou em scripts
> de shell desde a D001, mas dívida herdada (4 listas de serviços,
> scheduler paralelo, `register-mcp.sh` religando o outbox) e dois
> desvios do período (canary runner e resolver fora do pacote) seguem
> abertos. D004/D005/D006 foram rebaixadas para PARTIAL.

Descreve SOMENTE o estado existente no HEAD. Futuro planejado fica no
[MASTER-PLAN.md](MASTER-PLAN.md).

Atualizado em: 2026-07-21 (dashboard + D010-G0). O painel acima é a fonte de estado; as seções abaixo detalham camadas.

## Git

- branch: `codex/control-plane-redesign`
- HEAD: ver o painel no topo deste documento (fonte única). Esta seção
  descreve camadas, não estado de commit.
- staged: nenhum
- unstaged: nenhum
- untracked: 16 arquivos em `.tmp/` — LOCAL TEST ARTIFACT (canário
  Hermes 2026-07-18 + screenshots); não rastreados, não requeridos pelo
  produto, cleanup pendente de aprovação separada
- versão: 3.10.1 (worktree); runtime ativo em `D:\Hive-Mind` = 3.10.0

## Pacote nativo

| Componente | Local | Estado | Evidência |
|---|---|---|---|
| `hive-mind` (CLI) | `src/hive_mind/cli.py` + entry point em `pyproject.toml` | PARTIAL — só `--version` e `projects audit` | `tests/unit/test_f1_package.py`; commit `e215fd6`, `a44540b` |
| `hive-mindd` (daemon) | `src/hive_mind/daemon/{main,lock,supervisor}.py` | PARTIAL — `run --shadow` passivo (D007); managed ainda EX_UNAVAILABLE | `tests/unit/test_daemon_lock.py`, `test_shadow_supervisor.py`, `test_shadow_purity.py`, `test_daemon_run_shadow.py`; D007 |
| project root | `src/hive_mind/project.py` | DONE (escopo F1) | `tests/unit/test_f1_project_root.py` (151 L); commit `60aa2af` |
| projects audit | `core/projects/audit.py` + `src/hive_mind/cli.py:59-116` | DONE (unit + integração read-only) | `tests/unit/test_projects_audit.py` (127 L); `tests/integration/test_projects_audit_readonly.py`; commit `8a4a41f` |
| build (wheel+sdist) | `pyproject.toml` (hatchling) | DONE (escopo F1) | commits `6ac42f4`, `6f6dc64`; `uv build` < 5s |

## Código ainda legado

| Responsabilidade | Arquivo atual | Dono atual | Destino nativo (spec) | Estado |
|---|---|---|---|---|
| provider detection | `hive_mind.agents.detect` | **pacote** | — | **NATIVE** (D009) |
| MCP registration | `hive_mind.agents.{register,mcp_config,toml_config}` | **pacote** | — | **NATIVE** (D009, D009-R4); scripts ainda LEGACY_OWNER até D009-R6 |
| capture install | `scripts/setup/install-capture-hooks.py` | script | `hive_mind.agents` | **TO_REMOVE** — desligado de ambos os instaladores (D009-R3); porte nativo em D009-R5 |
| supervisor | `npm/lib/supervisor.js` + Task Scheduler | Node/OS | `hive-mindd` (F4–F5) | NOT_STARTED |
| scheduler | `register-windows-jobs.ps1` + systemd timers | scripts/OS | `hive-mindd` + APScheduler (F6–F7) | NOT_STARTED |
| services status | `scripts/setup/install_services.py::unit_definitions` | script | `hive_mind.daemon.manifest` (F2/F11) | NOT_STARTED |
| Dream Cycle | `scripts/dream/dream_cycle.py` | script | job nativo (F7) | NOT_STARTED (porte); defeito de agrupamento **corrigido** em D002 |
| project identity | `hive_mind.projects.identity` | **pacote** | — | **NATIVE** (D003-R1); legado é SHIM |

## Pipeline funcional

Legenda de estado: prova unitária ≠ OK operational. "UNIT" = coberto por
teste unitário/integração; "REAL" = comprovado com evento real pós-HEAD.

| Etapa | Estado | Evidência | Problema |
|---|---|---|---|
| provider source | REAL (D004) | canários provam cadeia inteira de ponta a ponta | — |
| parser | REAL (D004) | parsers validados nos canários multiagente | — |
| project identity | REAL (D003) | repo Git real + worktree real + registry entregue → `hive-mind`; **bug de normalização dupla corrigido**. Canário real (D004-R1): **4 passed / 4 failed / 4 skipped** | entrega de captura quebrada (D004-R2) |
| capture_core.ingest | REAL (D004) | ingestão bem sucedida no Claude Mem isolado dos canários | — |
| Claude Mem | REAL (D004) | `project_identity` gravado nos metadados da observação | dropdown com labels legados não migrados |
| bridge | REAL (D004) | `core/knowledge/claude_mem_bridge.py:401-435` grava `workspace_id = project_id` | — |
| UMC | REAL (D005) | observações no UMC promovidas para neurônios com `workspace_id` canônico e isolamento A/B provado | dados legados sem project_id não migrados |
| Dream Cycle | UNIT (D002) | agrupa por `project_id` via `resolve_observation_project()`; `fetch_balanced_observations` particiona por project_id; 18 unit + 6 integração SQLite real | falta prova operacional (ciclo real com modelos) |
| Markdown | UNIT (D002) | frontmatter com `project_id`, `project_name`, `identity_source`; path `cortex/temporal/<project_id>/<topic>/` | — |
| sqlite-vec | REAL (D005) | vetores e buscas isolados por workspace_id | — |
| Milvus | REAL (D005) | sincronização e expressões de filtro testados | sync_lag=568 em 2026-07-19 |
| Graphify | REAL (D005) | grafos estruturais mapeados e isolados por projeto | — |
| Graphiti | REAL (D005) | commit `7572756` isolou paths live | — |
| LightRAG | REAL (D005) | `test_lightrag_schema_selection.py` e isolamento E2E provados | — |
| REST | REAL (D005) | `scripts/services/sinapse-api.py` endpoints testados | — |
| MCP | UNIT (parcial) | `sinapse_health` respondendo em 2026-07-19 | registro ainda via scripts |
| CLI | PARTIAL | `hive-mind projects audit` existe | demais comandos ausentes |

## Saúde semântica (medição de 2026-07-19, runtime ativo)

| Métrica | Valor | Limiar | Estado |
|---|---:|---:|---|
| neurons_vectorized_pct | 93.61% | — | ok |
| observations_linked_pct | 7.62% | ≥80% | **degraded** |
| discoveries_pending | 942 | ≤500 | **degraded** |
| orphan_vectors | 7 | 0 | **degraded** |
| milvus_sync_lag (total) | 568 | 0 | atrasado |

`sinapse_health.status = degraded`. Não mascarar com "Ready: true".

## Fatos adicionais comprovados

- F1 de empacotamento implementada (commits `e215fd6`…`6f6dc64`);
- manifesto `config/runtime.yaml` implementado (Fase P2 instalada com D006);
- caminho experimental outbox (`capture-hook.py` → `CaptureQueue`)
  desabilitado no runtime novo (`cb7e3bd` + `b329e84`); arquivos e
  bancos históricos preservados (ADR-011);
- `D:\Hive-Mind\logs\capture-outbox.db` continua recebendo eventos do
  runtime ANTIGO — esperado; não alterar até P9;
- 2 testes pré-existentes falhando em
  `tests/unit/test_windows_install_contract.py`
  (UnicodeDecodeError lendo stdout PowerShell; reproduzido com e sem o
  diff de `b329e84`);
- 3 testes skipped em `tests/unit/test_register_mcp.py` no Windows
  (exigem POSIX shell);
- instalação Windows descartável NUNCA executada;
- canários anteriores (Antigravity IDE, Kimi, Qwen CLI, Qwen Desktop,
  Hermes) foram validados e complementados pelo teste E2E D005 (`test_e2e_memory_to_query_pipeline.py`).
