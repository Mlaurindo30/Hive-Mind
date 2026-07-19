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
| T1 | unit completo | unit | PARTIAL | `uv run pytest tests/unit -q -rs --timeout=300` | subconjuntos verdes; full não executado no HEAD; 2 falhas pré-existentes em `test_windows_install_contract.py` | sessão 2026-07-19 |
| T2 | integration completo | integration | NOT_STARTED | `uv run pytest tests/integration -q -rs --timeout=600` | — | — |
| T3 | e2e completo | operational | NOT_STARTED | `uv run pytest tests/e2e -q -rs --timeout=1200` | — | — |
| T4 | real completo | operational | NOT_STARTED | `uv run pytest tests/real -q -rs --timeout=1800` | — | — |
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
| C2 | Codex | operational | NOT_STARTED | canário pós-HEAD | — | — |
| C3 | Antigravity IDE | operational | NOT_STARTED | canário pós-HEAD | — | canário pré-correção passou (não vale) |
| C4 | Antigravity CLI | operational | NOT_STARTED | canário pós-HEAD | — | — |
| C5 | Kimi | operational | NOT_STARTED | canário pós-HEAD | — | canário pré-correção passou (não vale) |
| C6 | Qwen CLI | operational | NOT_STARTED | canário pós-HEAD | — | canário pré-correção passou (não vale) |
| C7 | Qwen Desktop | operational | NOT_STARTED | canário pós-HEAD | — | canário pré-correção passou (não vale) |
| C8 | Hermes (`C:\Users\miche\AppData\Local\hermes\state.db`) | operational | NOT_STARTED | canário pós-HEAD | — | canário 2026-07-18 é pré-correção |
| C9 | Mimo (`C:\Users\miche\.local\share\mimocode\mimocode.db`) | operational | NOT_STARTED | canário pós-HEAD | — | — |
| C10 | Kilo (fonte Windows real a documentar) | operational | NOT_STARTED | canário pós-HEAD | — | não usar paths Linux como prova |
| C11 | Copilot | operational | NOT_STARTED | canário pós-HEAD | — | — |
| C12 | OpenClaw (se instalado) | operational | NOT_STARTED | canário pós-HEAD | — | — |
| C13 | Roo / Screenpipe / SwarmClaw / demais detectados | operational | NOT_STARTED | canário pós-HEAD | — | — |

## Project identity

| Gate | Requisito | Tipo de prova | Estado | Comando | Resultado | Evidência |
|---|---|---|---|---|---|---|
| P1 | raiz e worktree → mesmo project_id | integration | PARTIAL | `pytest tests/integration/test_project_identity_git.py` | unit/integration verdes (82 testes, 2026-07-19) | falta prova operacional |
| P2 | aliases declarativos | unit | PARTIAL | `pytest tests/unit/test_project_identity.py` | verde | `config/project-aliases.yaml` |
| P3 | remote normalizado sem credenciais | unit | PARTIAL | idem | verde | `project_identity.py:86` |
| P4 | branch/worktree só metadados | unit | PARTIAL | idem | verde | falta prova real |
| P5 | Qwen/VS Code/miche/app/hermes não viram project_id | unit | PARTIAL | `pytest tests/unit/test_provider_parser_identity_contract.py` | verde | falta prova real |
| P6 | projeto A/B isolados | operational | NOT_STARTED | AUDIT-PROJECT-A/B | — | — |
| P7 | cross-project só quando solicitado | operational | NOT_STARTED | — | — | — |
| P8 | dropdown Claude Mem mostra um único Hive-Mind | operational | NOT_STARTED | inspeção pós-canário | — | labels legados exigem migração (D-futuro; sem autorização ainda) |

## Memória

| Gate | Requisito | Tipo de prova | Estado | Comando | Resultado | Evidência |
|---|---|---|---|---|---|---|
| M1 | Claude Mem recebe project canônico | unit | PARTIAL | `pytest tests/unit/test_capture_core.py` | verde | `capture_core.py:297` |
| M2 | bridge workspace_id=project_id | unit | PARTIAL | `pytest tests/unit/test_claude_mem_bridge.py` | verde (209 L de teste) | `claude_mem_bridge.py:435` |
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
| DC1 | agrupamento por project_id | unit | **FAILED (defeito confirmado)** | inspeção | `dream_cycle.py:71,812` usa `observations.project` texto livre; 0 refs a project_id | D002 corrige |
| DC2 | distiller real | operational | NOT_STARTED | — | — | — |
| DC3 | validator real | operational | NOT_STARTED | — | — | — |
| DC4 | router real | operational | NOT_STARTED | — | — | — |
| DC5 | Markdown em `cerebro/cortex/temporal/<project_id>/` | unit | NOT_STARTED | — | hoje usa label livre | D002 |
| DC6 | frontmatter canônico | unit | NOT_STARTED | — | ausente | D002 |
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
| R6 | readiness | NOT_STARTED | — | — | — | — |
| R7 | degraded/fail-closed sem mascarar | processo | PARTIAL | — | health reporta degraded honestamente | manter |

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
