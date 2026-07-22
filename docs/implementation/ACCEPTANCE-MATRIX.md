# Acceptance Matrix

Gate oficial do projeto. Estados: DONE somente para evidência
reproduzível no HEAD; PARTIAL para prova incompleta; NOT_STARTED para
não executado; BLOCKED somente com causa real registrada.

Tipos de prova: `unit` (mock permitido), `integration` (recursos reais
locais), `operational` (evento real, sem mock — obrigatório para aceite
final).

## Processo

| Gate | Requisito | Tipo de prova | Estado | Comando | Resultado | Evidência |
|---|---|---|---|---|---|---|
| X1 | documentação viva estabelecida | processo | DONE | `git show --stat ae32195` | 8 documentos, +1120 linhas | `docs/implementation/**`; D001 no ledger |
| X2 | MASTER-PLAN aprovado | processo | DONE | — | aprovado em 2026-07-19 | MASTER-PLAN §Baseline |
| X3 | namespace de agentes decidido | processo | DONE | — | `hive_mind.agents` | ADR-013 ACCEPTED |
| X4 | toda entrega atualiza ledger + current-state + matriz | processo | IN_PROGRESS | revisão por entrega | regra ativa a partir de D002 | README §Regras |

## Build

| Gate | Requisito | Tipo de prova | Estado | Comando | Resultado | Evidência |
|---|---|---|---|---|---|---|
| B1 | compileall limpo | build | NOT_STARTED | `uv run python -m compileall src core scripts plugins integrations` | — | — |
| B2 | uv build (sdist+wheel) | build | PARTIAL | `uv build` | passou na F1 (<5s) | commits `6ac42f4`, `6f6dc64`; não re-executado no HEAD |
| B3 | wheel sem `.env`/`uv.lock`/`.github` | build | PARTIAL | inspeção do wheel | passou na F1 | commit `6f6dc64` |
| B4 | instalação com dependências | operational | NOT_STARTED | pip install do wheel em venv limpa | — | — |
| B5 | execução fora do repositório | operational | NOT_STARTED | `hive-mind --version` fora do repo | — | — |

## Testes

| Gate | Requisito | Tipo de prova | Estado | Comando | Resultado | Evidência |
|---|---|---|---|---|---|---|
| T1 | unit completo | unit | PARTIAL | `uv run pytest tests/unit -q -rs --timeout=300` | **993 passed, 20 skipped, 2 failed** (137s) | D002, 2026-07-19; as 2 falhas são pré-existentes em `test_windows_install_contract.py` (UnicodeDecodeError de stdout PowerShell) |
| T2 | integration completo | integration | NOT_STARTED | `uv run pytest tests/integration -q -rs --timeout=600` | — | — |
| T3 | e2e completo | operational | NOT_STARTED | `uv run pytest tests/e2e -q -rs --timeout=1200` | — | — |
| T4 | real completo | operational | PARTIAL | `pytest tests/real -q -rs` | passou nos canários multiagente e bridge | D004, `test_canary_multiagent_pipeline.py` |
| T5 | npm test | unit | NOT_STARTED | `npm test` | — | — |
| T6 | cargo test | unit | NOT_STARTED | `cargo test --release` | — | — |
| T7 | cargo build | build | NOT_STARTED | `cargo build --release` | — | — |
| T8 | inventário de skips | processo | NOT_STARTED | `-rs` em todas as suítes | — | — |

## Captura por provider (prova operacional obrigatória)

Cada linha exige: fonte real → parser → project_id → capture_core.ingest
→ Claude Mem search → timeline → get_observations → bridge →
workspace_id → sem duplicação. Adapter existir NÃO é evidência.

| Gate | Provider | Tipo de prova | Estado | Comando | Resultado | Evidência |
|---|---|---|---|---|---|---|
| C1 | Claude Code (captura nativa) | operational | NOT_STARTED | canário pós-HEAD | — | canários anteriores são pré-correção |
| C2 | Codex | operational | **FAILED** | `hive-mind validate agents` | canário real: ver AUDIT | **D004** — gate de provider. Corrigido em D004-R1: a evidência anterior era mockada (sessão sintética + monkeypatch), viola regra 5 do README |
| C3 | Antigravity IDE | operational | **FAILED** | `hive-mind validate agents` | canário real: ver AUDIT | **D004** — gate de provider. Corrigido em D004-R1: a evidência anterior era mockada (sessão sintética + monkeypatch), viola regra 5 do README |
| C4 | Antigravity CLI | operational | **FAILED** | `hive-mind validate agents` | canário real: ver AUDIT | **D004** — gate de provider. Corrigido em D004-R1: a evidência anterior era mockada (sessão sintética + monkeypatch), viola regra 5 do README |
| C5 | Kimi | operational | **FAILED** | `hive-mind validate agents` | canário real: ver AUDIT | **D004** — gate de provider. Corrigido em D004-R1: a evidência anterior era mockada (sessão sintética + monkeypatch), viola regra 5 do README |
| C6 | Qwen CLI | operational | NOT_STARTED | canário pós-HEAD | — | canário pré-correção passou (não vale) |
| C7 | Qwen Desktop | operational | NOT_STARTED | canário pós-HEAD | — | canário pré-correção passou (não vale) |
| C8 | Hermes (`C:\Users\miche\AppData\Local\hermes\state.db`) | operational | **FAILED** | `hive-mind validate agents` | canário real: ver AUDIT | **D004** — gate de provider. Corrigido em D004-R1: a evidência anterior era mockada (sessão sintética + monkeypatch), viola regra 5 do README |
| C9 | Mimo (`C:\Users\miche\.local\share\mimocode\mimocode.db`) | operational | **FAILED** | `hive-mind validate agents` | canário real: ver AUDIT | **D004** — gate de provider. Corrigido em D004-R1: a evidência anterior era mockada (sessão sintética + monkeypatch), viola regra 5 do README |
| C10 | Kilo (fonte Windows real a documentar) | operational | **FAILED** | `hive-mind validate agents` | canário real: ver AUDIT | **D004** — gate de provider. Corrigido em D004-R1: a evidência anterior era mockada (sessão sintética + monkeypatch), viola regra 5 do README |
| C11 | Copilot | operational | **FAILED** | `hive-mind validate agents` | canário real: ver AUDIT | **D004** — gate de provider. Corrigido em D004-R1: a evidência anterior era mockada (sessão sintética + monkeypatch), viola regra 5 do README |
| C12 | OpenClaw (se instalado) | operational | **FAILED** | `hive-mind validate agents` | canário real: ver AUDIT | **D004** — gate de provider. Corrigido em D004-R1: a evidência anterior era mockada (sessão sintética + monkeypatch), viola regra 5 do README |
| C13 | Roo / Screenpipe / SwarmClaw / demais detectados | operational | **FAILED** | `hive-mind validate agents` | canário real: ver AUDIT | **D004** — gate de provider. Corrigido em D004-R1: a evidência anterior era mockada (sessão sintética + monkeypatch), viola regra 5 do README |

## Agent integrations (hive_mind.agents, D009)

| Gate | Requisito | Tipo de prova | Estado | Comando | Resultado | Evidência |
|---|---|---|---|---|---|---|
| AG1 | detecção nativa de providers | unit+operational | DONE | `pytest tests/unit/test_agents_detect.py` + `hive-mind agents detect` | 9 passed; detect real 9/13 bate com canário D004 | D009 fatia 1; ADR-013 |
| AG2 | merge MCP transacional (backup/atomic/dry-run) | unit+operational | DONE | `pytest tests/unit/test_agents_mcp_config.py` + demo em config temp | 10 passed; terceiros preservados, legados removidos, JSON inválido recusado sem clobber, idempotente | D009 fatia 2 |
| AG2b | `agents register` (mapa provider→config) | unit+operational | PARTIAL | `pytest tests/unit/test_agents_register.py` + dry-run real | 9 passed; dry-run resolveu 11 alvos reais sem escrever nada | D009 fatia 3; `--apply` não executado (decisão do usuário) |
| AG2c | writer TOML (Codex `config.toml`) | unit+operational | DONE | `pytest tests/unit/test_agents_toml_config.py` + merge em cópia do config real | 13 passed; terceiros e comentários preservados, subtabelas substituídas, idempotente, original intocado | D009-R4; tomlkit |
| AG3 | instalação de instruções | unit+operational | **DONE_TEMP_CONFIG** | `pytest tests/unit/test_agents_doctor.py::TestInstruction*` + apply em `tmp_path` | 14 passed; bloco gerenciado idempotente, bloco da era PowerShell substituído sem duplicar, conteúdo do usuário preservado | D009-R5; nenhum arquivo de instrução real tocado |
| AG4 | `agents doctor` | unit+operational | **DONE_READ_ONLY_REAL** | `pytest tests/unit/test_agents_doctor.py::TestDoctor` + `hive-mind agents doctor` no host | 5 passed; diagnóstico real leu configs reais **sem escrever**; `which` injetável impede vazamento do PATH do host | D009-R5 |
| AG5 | wrappers PS1/SH mínimos | unit+integration | **DONE_TEMP_CONFIG** | `pytest tests/unit/test_registration_wrappers.py tests/integration/test_registration_through_wrappers.py` | 56 + 23 passed; PS1 456→55 L, SH 444→50 L; repasse fiel (ordem, espaços, Unicode, metacaracteres), streams e exit codes preservados; cadeia completa wrapper→CLI→config provada em HOME/APPDATA/project temporários | D009-R6; nenhum config real tocado |
| AG8 | contrato CLI legado preservado | unit+integration | **DONE_TEMP_CONFIG** | `hive_mind.agents.compat` + testes acima | `--only/--self/--agent`, posicional, `--check`, `--list`, `--no-instructions`, `--codex-only`, `--claude-only`, `HIVE_SKIP_PROMPT`, exit 2 para agente inválido | D009-R6; tradução em Python, nunca no shell |
| AG9 | `--check` como gate real | unit+integration | **DONE_READ_ONLY_REAL** | `pytest tests/integration/test_register_mcp_check.py` | 3 passed; exit 0 sse todo provider **detectado** está configurado; provider ausente não é falha; no host real sai 1 e reporta 1 de 9 saudáveis | D009-R6; substitui R5.4 (`--check` sempre 0), que tornava o gate inútil |
| AG6 | `agents unregister` | unit+operational | **DONE_TEMP_CONFIG** | `pytest tests/unit/test_agents_doctor.py::TestUnregister` | 5 passed; remove só a entrada `sinapse-memory`, preserva MCP de terceiros em JSON e TOML, idempotente | D009-R5; nenhum config real alterado |
| AG7 | captura nativa por provider | — | **NOT_APPLICABLE_BY_ARCHITECTURE** | — | a captura não é registrada por provider: o caminho canônico é `provider/parser → sessão normalizada → capture_core.ingest → Claude Mem` (ADR-004). Instalar hooks por agente reintroduziria o outbox deprecado | ADR-004; entrega real é D004-R2 |

## Project identity

| Gate | Requisito | Tipo de prova | Estado | Comando | Resultado | Evidência |
|---|---|---|---|---|---|---|
| P1 | raiz e worktree → mesmo project_id | integration | DONE | `pytest tests/integration/test_project_identity_pipeline.py` | 17 passed; repo Git real + worktree real + registry entregue → `hive-mind` | D003 |
| P2 | aliases declarativos | integration | DONE | idem | passed; **corrigido bug que tornava `remotes:` código morto** | D003; `config/project-aliases.yaml` |
| P3 | remote normalizado sem credenciais | integration | DONE | `pytest tests/integration/test_project_identity_git.py` | passed (https/ssh/scp) | `project_identity.py:86` |
| P4 | branch/worktree só metadados | integration | DONE | `test_worktree_name_and_branch_stay_metadata` | passed | D003 |
| P5 | Qwen/VS Code/miche/app/hermes não viram project_id | integration | DONE | `TestSurfacesAreNotProjects` | 6 passed; superfícies → `unclassified/*` | D003 |
| P6 | projeto A/B isolados | integration | PARTIAL | `pytest tests/real/test_canary_multiagent_pipeline.py` | PARTIAL | isolamento A/B provado em SQLite real (D003); canário real D004-R1: 4 passed / 4 failed / 4 skipped |
| P7 | cross-project só quando solicitado | integration | PARTIAL | `test_two_projects_stay_isolated_and_filter_cleanly` | passed | falta prova via consulta real (D005) |
| P8 | dropdown Claude Mem mostra um único Hive-Mind | integration | PARTIAL | `test_root_and_worktree_sessions_show_one_dropdown_entry` | passed no campo `project` da sessão | falta observar a UI com eventos reais (D004); labels legados exigem migração autorizada |

## Memória

| Gate | Requisito | Tipo de prova | Estado | Comando | Resultado | Evidência |
|---|---|---|---|---|---|---|
| M0 | entrega ao Claude Mem | operational | **OPERATIONAL** | leitura `mode=ro` de `claude-mem.db` (D004-R2) | 5.220 observações, 1.710 prompts, 662 sumários; escrita hoje. Entrega **não** está parada | errata D004-R2 |
| M1 | Claude Mem recebe project canônico | integration | **DONE** | `pytest tests/integration/test_capture_isolated_worker_delivery.py` | 31 passed; **2 observations reais** geradas por modelo local, `project='Hive-Mind'` canônico, rótulo livre ausente | D004-R2W; provider Ollama, sem credencial |
| M13 | provider local sem credencial | integration | **DONE** | `TestTheProviderIsLocalAndCredentialFree` | slot OpenAI-compat com `base_url` em localhost e chave literal `local`; nenhum `_API_KEY`/`_TOKEN` com valor real | D004-R2W |
| M14 | envelope canônico sobrevive até a observation | integration | **FAILED** | `test_the_identity_envelope_does_not_survive_into_observations` | `observations.metadata` é NULL e `session_summaries` não tem coluna metadata. O nome canônico chega; o `project_id` não | **D004-R2**; sem ele o bridge grava `workspace_id` legacy |
| M15 | nada ativo alterado | processo | **DONE** | `TestNothingActiveIsTouched` | 11 guardas: settings real, setup-brain, sync-provider, `CLAUDE_CONFIG_DIR`, HOME/USERPROFILE/APPDATA/LOCALAPPDATA/TEMP, porta viva, store viva, ambiente construído e não filtrado | D004-R2W |
| M11 | ambiente do worker sem credencial do host | integration | **DONE** | `TestTheWorkerEnvironmentCarriesNoCredentials` | 4 passed; ambiente por allowlist, nomes de credencial subtraídos, HOME/USERPROFILE/APPDATA/LOCALAPPDATA/CLAUDE_CONFIG_DIR temporários | D004-R2W; SEC-001 |
| M12 | fronteira do LLM declarada | integration | **DONE** | `TestTheLlmBoundaryIsExplicit` | worker isolado responde `Not logged in`; observations=0 asseverado como estado conhecido | D004-R2W |
| SEC1 | credencial exposta contida | processo | **BLOCKED** | `hive_mind.security.secret_scan` | 0 ocorrências em worktree, staged, mensagens e 14.973 objetos Git | **SEC-001**; exige rotação humana |
| M2 | bridge workspace_id=project_id | integration | **DONE** | `test_the_bridge_carries_project_id_into_umc_workspace_id` | bridge de **produção** contra `CLAUDE_MEM_DB` e `SINAPSE_HOME` temporários; `workspace_id` gravado = `project_id` canônico | D004-R2; evidência: stores temporárias |
| M5 | ponto único de enforcement | unit | **DONE** | `pytest tests/unit/test_capture_canonical_identity.py` | 39 passed; `capture_core` é shim (0 definições), transporte recusa sessão sem envelope, nenhum entrypoint chama `attach_project_identity` | D004-R2 |
| M6 | worktree e raiz = um projeto | unit+integration | **DONE** | `test_a_worktree_and_its_root_are_one_project` | repositório e worktree **reais** via `git worktree add`; defeito encontrado e corrigido: `project_name` vinha do basename da worktree | D004-R2; verificado no repositório real |
| M7 | prompt nunca vira projeto | unit | **DONE** | `TestTheFreeLabelIsNotAuthority` | 9 rótulos reais de produção testados, incluindo `preciso-que-verifique-o-por-que-3` e `referenced-chatgpt-conversation-*` | D004-R2 |
| M8 | matriz por provider | operational | **NOT_STARTED** | — | um evento verde prova o caminho, não os 13 providers. Estados por provider: PASS/FAIL/NO_SOURCE/NOT_INSTALLED/BLOCKED_BY_PROVIDER — **sem SKIP genérico** | **D004-M** |
| M9 | worker isolável sem alterar o vivo | integration | **DONE** | `TestTheRealWorkerStoresCanonicalIdentity::test_the_worker_is_isolated_from_the_live_one` | `CLAUDE_MEM_DATA_DIR` tem precedência; pid, banco e settings saem do mesmo diretório; porta livre ≠ 37700 | D004-R2W |
| M10 | manifesto declara o worker que existe | — | **FAILED** | `TestTheManifestDisagreesWithReality` | `runtime.yaml` diz `python -m claude_mem.worker`; o módulo **não é importável** e o processo vivo é `bun worker-service.cjs` | **D006-R2** |
| M3 | outbox backlog ≠ falha de entrega | operational | **DONE_READ_ONLY_REAL** | leitura `mode=ro` dos 2 outboxes | `attempts=0`, `last_error=0`, `dead_letter=0` em 20.649 linhas: nunca houve tentativa. Fila sem dono (ADR-004), não entrega falhada | errata D004-R2 |
| M4 | writers dos outboxes identificados | processo | **DONE** | `~/.claude/settings.json`, `~/.codex/hooks.json` | ambos são `capture-hook.py`: claude = `LEGACY_ACTIVE_WRITER`, codex/antigravity/mimo = `LEGACY_INACTIVE_WRITER` desde 20/07. Zero UNKNOWN | D004-R2; nenhum desligado |
| M3 | UMC filtra por project_id | integration | NOT_STARTED | — | — | — |
| M4 | FTS | operational | NOT_STARTED | — | — | — |
| M5 | sqlite-vec com metadata de projeto | operational | NOT_STARTED | — | — | — |
| M6 | Milvus com metadata de projeto | operational | NOT_STARTED | — | sync_lag=568 em 2026-07-19 | — |
| M7 | Graphify project_id em nós/relações | operational | NOT_STARTED | — | — | — |
| M8 | Graphiti project_id | operational | NOT_STARTED | — | — | — |
| M9 | LightRAG sem vazamento cross-project | operational | NOT_STARTED | — | — | `test_lightrag_schema_selection.py` cobre só seleção de schema |

## Dream Cycle

| Gate | Requisito | Tipo de prova | Estado | Comando | Resultado | Evidência |
|---|---|---|---|---|---|---|
| DC1 | agrupamento por project_id | unit | DONE | `pytest tests/unit/test_dream_project_identity.py tests/integration/test_dream_project_isolation.py` | 24 passed | D002; `resolve_observation_project()` + partição SQL por project_id |
| DC2 | distiller real | operational | NOT_STARTED | — | — | — |
| DC3 | validator real | operational | NOT_STARTED | — | — | — |
| DC4 | router real | operational | NOT_STARTED | — | — | — |
| DC5 | Markdown em `cerebro/cortex/temporal/<project_id>/` | unit | DONE | `pytest tests/unit/test_dream_project_identity.py::TestCanonicalFrontmatter` | passed | D002; `note_file = cp.TEMPORAL / proj / safe_topic` com proj = project_id |
| DC6 | frontmatter canônico | unit | DONE | idem | passed | D002; `project_id`, `project_name`, `identity_source` |
| DC7 | integrity_hash | unit | PARTIAL | — | hash existe no frontmatter atual | formato canônico pendente |
| DC8 | reindex pós-escrita | operational | NOT_STARTED | — | — | — |
| DC9 | consulta com citação | operational | NOT_STARTED | — | — | — |

## Backup (D008-R1B)

| Gate | Requisito | Tipo de prova | Estado | Comando | Resultado | Evidência |
|---|---|---|---|---|---|---|
| BK1 | motor nativo (SQLite backup API) | unit | DONE | `pytest tests/unit/test_maintenance_backup.py` | 25 passed | portado de `backup_databases.py` |
| BK2 | retenção só após verificação | unit | DONE | `test_a_failed_run_never_prunes` | passed | corrige defeito do motor legado |
| BK3 | lock de execução única | unit | DONE | `TestLock` | 3 passed | `MaintenanceLock` |
| BK4 | manifesto + SHA-256 + verify | unit | DONE | `TestManifestAndVerify` | 6 passed | detecta tamper/truncado/ausente |
| BK5 | restore em diretório alternativo | unit+operational | **DONE_SYNTHETIC** | `TestRestore` + prova sintética | 500 registros idênticos, `integrity_check ok`, `foreign_key_check` vazio | dados sintéticos |
| BK6 | backup de dados reais | operational | **NOT_EXECUTED** | — | exige autorização | — |
| BK7 | restore de dados reais | operational | **NOT_EXECUTED** | — | exige autorização | — |

## Runtime

| Gate | Requisito | Tipo de prova | Estado | Comando | Resultado | Evidência |
|---|---|---|---|---|---|---|
| R1 | local-min bootável | operational | NOT_STARTED | — | — | — |
| R2 | local-full bootável | PARTIAL | integration | commit `05d8900` corrigiu perfis | não re-validado no HEAD |
| R3 | supervisor único | design | NOT_STARTED | — | hoje Node + Task Scheduler | P4 |
| R4 | scheduler único | design | NOT_STARTED | — | múltiplos owners hoje | P4 |
| R5 | health | PARTIAL | operational | `sinapse_health` | respondeu 2026-07-19, status degraded | runtime antigo |
| R6 | readiness | DONE | operational | `hive-mindd run --shadow --serve` + `curl /ready` | D007: HTTP `/ready` real → 200 quando required ready, 503 fail-closed | named socket loopback real |
| R7 | degraded/fail-closed sem mascarar | operational | DONE | `curl /health /ready` reais | `/health` reporta `degraded`, `/ready` 503 sem observação | D007 fatia 2 |
| R8 | instância única do daemon | unit | DONE | `pytest tests/unit/test_daemon_lock.py` | 6 passed, 1 skipped (POSIX) | D007; named mutex Windows / flock POSIX |
| R9 | shadow passivo (sem mutação) | unit+operational | DONE | `pytest tests/unit/test_shadow_purity.py` + `hive-mindd run --shadow` real | 5 passed; run real gravou só `services.shadow.json`, iniciou nada | D007; spec Anexo D.4 |
| R10 | HTTP loopback só leitura | unit+operational | DONE | `pytest tests/unit/test_daemon_http_routes.py` + `curl -X POST /stop` real | 9 passed; `POST /stop` → 404; só `/health` `/ready` `/metrics` | D007 fatia 2; spec §15.1/§15.4 |
| R11 | `service status` CLI (leitura) | unit+operational | DONE | `pytest tests/unit/test_cli_service_status.py` + fluxo real | 4 passed; `run --shadow` → `service status` listou 7 serviços | D007 fatia 3 |
| R12 | socket de controle autenticado (§15.2/§15.3) | unit+operational | DONE | `pytest tests/unit/test_control_*.py` + `hive-mind service ping` real | 16 passed; named pipe real com DACL per-user; `pong` ponta a ponta | D008 fatia 1 |
| R13 | shadow recusa mutação pelo socket | unit+operational | DONE | `test_shadow_refusal_travels_over_the_real_socket` | passed; `stop` recusado sobre o fio real | D008 fatia 1; Anexo D.4 |
| R14 | supervisor managed (inicia/para serviços) | unit+operational | DONE | `pytest tests/unit/test_managed_supervisor.py` + demo real | 8 passed; 2 serviços sintéticos iniciados em ordem de dependência, PIDs reais, parados e confirmados mortos | D008 fatia 2; sem cutover no runtime ativo |
| R15 | restart policy monitor | unit | DONE | `pytest tests/unit/test_managed_restart.py` | 6 passed; on-failure/always reiniciam, never não, restart_limit cobre crashloop, stop intencional não dispara | D008 fatia 3 |
| R16b | inventário de jobs validado semanticamente | processo | DONE | D008-R1V | 18 jobs vivos classificados; 1 job morto (`backup`) removido | `docs/scheduler.md` |
| R16c | ordenação bridge→dream como dependência declarada | unit | DONE | `pytest tests/unit/test_job_dependencies.py` | 9 passed; schema `depends_on` + policy, ciclo/fantasma rejeitados | D008-R1V |
| R16d | execução real dos 18 jobs | operational | NOT_STARTED | — | daemon só calcula em shadow; não dispara | F7/D010 |
| R16e | enforcement da dependência em runtime (falha/atraso/reboot/misfire) | operational | NOT_STARTED | — | exige scheduler disparando | F7/D010 |
| R16f | backup restaurável | operational | **DONE_SYNTHETIC** | `TestRestore` + prova sintética (BK5) | 500 registros idênticos, `integrity_check ok`, `foreign_key_check` vazio — em banco sintético | restauração de banco **real** continua NOT_EXECUTED (BK7) |
| R16 | shadow scheduler (calcula next-run) | unit+operational | DONE | `pytest tests/unit/test_shadow_scheduler.py` + real | 10 passed; jobs do manifesto: dream-cycle→03:00, tailer→+30s; dispara nada | D008 fatia 4; spec F6/D.6 |
| R17 | persistência do scheduler (SQLite, sobrevive restart) | unit+operational | DONE | `pytest tests/unit/test_sqlite_scheduler_store.py` + demo restart | 9 passed; next-run sobreviveu a nova instância do store com timezone | D008 fatia 5; spec D.6 |
| R18 | disparo de jobs managed / cutover journal / cutover real | — | NOT_STARTED | — | F7 firing (store pronto) + journal (D.3) + cutover (D010, gate humano) | D010 |

## Windows lifecycle

| Gate | Requisito | Tipo de prova | Estado | Comando | Resultado | Evidência |
|---|---|---|---|---|---|---|
| W1 | install limpo | operational | NOT_STARTED | ambiente descartável | — | — |
| W2 | reboot | operational | NOT_STARTED | — | — | — |
| W3 | post-reboot | operational | NOT_STARTED | — | — | — |
| W4 | repair | operational | NOT_STARTED | — | — | — |
| W5 | update | operational | NOT_STARTED | — | — | — |
| W6 | rollback | operational | NOT_STARTED | — | — | — |
| W7 | uninstall | operational | NOT_STARTED | — | — | — |
| W8 | reinstall | operational | NOT_STARTED | — | — | — |

## Integridade de dados

| Gate | Requisito | Tipo de prova | Estado | Comando | Resultado | Evidência |
|---|---|---|---|---|---|---|
| I1 | foreign_key_check vazio | operational | NOT_STARTED | `PRAGMA foreign_key_check` | — | — |
| I2 | integrity_check ok | operational | NOT_STARTED | `PRAGMA integrity_check` | — | — |
| I3 | observations_linked_pct ≥80% | operational | FAILED | `sinapse_health` | 7.62% em 2026-07-19 | runtime antigo; P1/F |
| I4 | discoveries_pending ≤500 | operational | FAILED | idem | 942 | idem |
| I5 | orphan_vectors = 0 | operational | FAILED | idem | 7 | idem |
| I6 | sessions/observations/vectors/markdown sem project_id contabilizados | operational | NOT_STARTED | `hive-mind projects audit` | — | comando existe (`8a4a41f`) |
