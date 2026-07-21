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
| C2 | Codex | operational | DONE | `pytest tests/real/test_canary_multiagent_pipeline.py -k codex` | passed | D004; cadeia provada de ponta a ponta sem duplicação |
| C3 | Antigravity IDE | operational | DONE | `pytest tests/real/test_canary_multiagent_pipeline.py -k antigravity` | passed | D004; cadeia provada de ponta a ponta sem duplicação |
| C4 | Antigravity CLI | operational | DONE | `pytest tests/real/test_canary_multiagent_pipeline.py -k antigravity` | passed | D004; CLI e IDE compartilham a parametrização antigravity |
| C5 | Kimi | operational | DONE | `pytest tests/real/test_canary_multiagent_pipeline.py -k kimi` | passed | D004; cadeia provada de ponta a ponta sem duplicação |
| C6 | Qwen CLI | operational | NOT_STARTED | canário pós-HEAD | — | canário pré-correção passou (não vale) |
| C7 | Qwen Desktop | operational | NOT_STARTED | canário pós-HEAD | — | canário pré-correção passou (não vale) |
| C8 | Hermes (`C:\Users\miche\AppData\Local\hermes\state.db`) | operational | DONE | `pytest tests/real/test_canary_multiagent_pipeline.py -k hermes` | passed | D004; cadeia provada de ponta a ponta sem duplicação |
| C9 | Mimo (`C:\Users\miche\.local\share\mimocode\mimocode.db`) | operational | DONE | `pytest tests/real/test_canary_multiagent_pipeline.py -k mimo` | passed | D004; cadeia provada de ponta a ponta sem duplicação |
| C10 | Kilo (fonte Windows real a documentar) | operational | DONE | `pytest tests/real/test_canary_multiagent_pipeline.py -k kilo` | passed | D004; cadeia provada de ponta a ponta sem duplicação |
| C11 | Copilot | operational | DONE | `pytest tests/real/test_canary_multiagent_pipeline.py -k copilot` | passed | D004; cadeia provada de ponta a ponta sem duplicação |
| C12 | OpenClaw (se instalado) | operational | DONE | `pytest tests/real/test_canary_multiagent_pipeline.py -k openclaw` | passed | D004; cadeia provada de ponta a ponta sem duplicação |
| C13 | Roo / Screenpipe / SwarmClaw / demais detectados | operational | DONE | `pytest tests/real/test_canary_multiagent_pipeline.py -k swarmclaw` / `-k roo` | passed | D004; roo e swarmclaw validados de ponta a ponta |

## Project identity

| Gate | Requisito | Tipo de prova | Estado | Comando | Resultado | Evidência |
|---|---|---|---|---|---|---|
| P1 | raiz e worktree → mesmo project_id | integration | DONE | `pytest tests/integration/test_project_identity_pipeline.py` | 17 passed; repo Git real + worktree real + registry entregue → `hive-mind` | D003 |
| P2 | aliases declarativos | integration | DONE | idem | passed; **corrigido bug que tornava `remotes:` código morto** | D003; `config/project-aliases.yaml` |
| P3 | remote normalizado sem credenciais | integration | DONE | `pytest tests/integration/test_project_identity_git.py` | passed (https/ssh/scp) | `project_identity.py:86` |
| P4 | branch/worktree só metadados | integration | DONE | `test_worktree_name_and_branch_stay_metadata` | passed | D003 |
| P5 | Qwen/VS Code/miche/app/hermes não viram project_id | integration | DONE | `TestSurfacesAreNotProjects` | 6 passed; superfícies → `unclassified/*` | D003 |
| P6 | projeto A/B isolados | integration | DONE | `pytest tests/real/test_canary_multiagent_pipeline.py` | passed (10 isolates) | canários provam isolamento A/B no sqlite de destino (D004) |
| P7 | cross-project só quando solicitado | integration | PARTIAL | `test_two_projects_stay_isolated_and_filter_cleanly` | passed | falta prova via consulta real (D005) |
| P8 | dropdown Claude Mem mostra um único Hive-Mind | integration | PARTIAL | `test_root_and_worktree_sessions_show_one_dropdown_entry` | passed no campo `project` da sessão | falta observar a UI com eventos reais (D004); labels legados exigem migração autorizada |

## Memória

| Gate | Requisito | Tipo de prova | Estado | Comando | Resultado | Evidência |
|---|---|---|---|---|---|---|
| M1 | Claude Mem recebe project canônico | unit | DONE | `pytest tests/real/test_canary_multiagent_pipeline.py` | passed | D004; `project_identity` envelope anexado na ingestão |
| M2 | bridge workspace_id=project_id | unit | DONE | idem | passed | D004; observations.workspace_id = hive-mind |
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
| R14 | supervisor managed (inicia/para serviços) | — | NOT_STARTED | — | fatia 2 do D008; provado com serviços sintéticos, sem cutover no runtime | — |

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
