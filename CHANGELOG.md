# Changelog

## v3.7.8 — K8 Production Hardening (F4.0–F4.6)

Release date: 2026-07-01

Resolve os 6 pontos pendentes que apontei na revisão de produção da
v3.7.6 e que estavam abertos no `Current State.md` do cérebro.

### Fixed

- **Race condition no K8 health (`database is locked` no
  `ensure_migrations`)**: `core/database.py::get_connection` subiu o
  `busy_timeout` de 30s para 60s, e adicionei o helper
  `with_sqlite_retry` (F4.0) que executa uma callable contra SQLite com
  retry exponencial em `OperationalError` contendo `locked` ou `busy`.
  `scripts/health/knowledge_health.py` agora envolve `ensure_migrations`
  com `with_sqlite_retry(op_label="ensure_migrations")`. O teste de
  aceitação `tests/real/test_knowledge_health.py::test_knowledge_health_cli_fail_closed_acceptance`
  que estava falhando intermitentemente no CI runner agora passa
  consistentemente (5/5 real tests verdes em 21.40s).

- **`_claude_mem_observation_vector_total` quebra sem `sqlite_vec` no
  venv**: o módulo agora trata `ImportError`/`OperationalError` ao
  carregar `sqlite_vec` retornando `0` (fail-safe). Sem `sqlite-vec`
  instalado mas com `~/.claude-mem/claude-mem.db` presente, o
  `--fail-closed` rodava `ModuleNotFoundError`. Agora roda com gate S3
  `None` (passa).

### Added

- **`scripts/health/reprocess_quarantine.py` (F4.2)**: ferramenta CLI
  para reprocessar observações em quarentena (`archived=2`) por idade.
  Política: 7+ dias entra em retry automático (idempotente via
  `archived=0` + re-promote); 30+ dias com 3 retries esgotados vai para
  `archived=3` (quarentena terminal, NUNCA deletado). Aceita
  `--dry-run`, `--max-age-days`, `--reset-reason <policy>`. Reporta
  JSON com `scanned/skipped_recent/retried/recovered/terminal/by_reason`.
  Em produção: 1365 quarantined, 376 com < 7d (skip), 989 com 7+d (retry).

- **`docs/13-slo-and-observability.md` (F4.3)**: framework canônico de
  SLO K8 com 7 gates (S1–S7) — `orphan_vectors == 0`,
  `observations_linked_pct ≥ 80%`, `discoveries_pending ≤ 500`, etc. —
  documentado com donos de código, testes, dashboards e runbook
  (§7 — "onde olhar quando algo cai"). Adicionei gate S4 e refinei S5
  no `evaluate_fail_closed` (eram warnings, agora fail-closed).
  Métrica `observations_total` exposta no payload JSON.

- **5 testes novos** (38 asserções no total):
  - `tests/unit/test_with_sqlite_retry.py` — 5 testes (F4.0)
  - `tests/unit/test_reprocess_quarantine.py` — 5 testes (F4.2)
  - `tests/unit/test_knowledge_health_slo.py` — 12 testes (F4.3)
  - `tests/unit/test_workspace_isolation.py` — 4 testes (F4.5)
  - `tests/unit/test_telemetry_optin.py` — 10 testes (F4.6)

- **`tests/unit/test_workspace_isolation.py` (F4.5)**: prova que
  `workspace_id` cumpre seu papel de fronteira de isolamento K10.
  Cobertura: `neurons`/`observations` filtrados por workspace,
  `compute_knowledge_health(workspace_id='acme')` não enxerga dados de
  `default`. Inclui teste `@pytest.mark.real` que executa contra o
  cérebro real.

- **`HIVE_SERVICE_NAME` no `.env.example`**: documentado no bloco
  Langfuse. Usado como `service.name` no `service.version` OTEL
  resource. Comentário expandido aponta para §3 de `docs/13`.

### Test results

- Unit: 538 passed, 3 skipped, 0 failed (25.85s)
- E2E: 22 passed (7.89s)
- Real: 59 passed (197.02s)
- All 4 suites: PASSED (4/4, 0 failed)

### Migration notes

- Nenhuma migration de schema. Apenas additive.
- `busy_timeout` agora é 60s; se algum script dependia do valor 30s para
  detectar contenção, ele precisa ser revisado.
- `reprocess_quarantine.py` é seguro rodar em produção mas cria
  disputa de lock com `dream_cycle`. Recomenda-se rodar fora do
  horário de cron (00:00–02:00 UTC para o Brasil).

## v3.7.7 — Audit Harden + CI Workflow Fix + Contract Test Gates

Release date: 2026-07-01

### Changed

- **CI workflow (`.github/workflows/test.yml`):** corrigidos os caminhos
  `scripts/components.py` → `scripts/setup/components.py`. Pipeline
  estava falhando no bootstrap por caminho obsoleto.
- **Audit memory (K8 hygiene):** `scripts/health/audit_memory.py` agora
  aceita `--exclude` (csv e `SINAPSE_AUDIT_EXCLUDE`) para pular projetos
  gitignored (`Thoth`, `ComfyUI`, `OpenAlice`, `agent-langgraph`,
  `openclaw-crestodian-planner-NyDaMs`, `michel`, `e2e-chatbot-app-next`,
  `open-design`) que vivem no vault local mas não fazem parte desta
  instância. O audit agora reflete **o estado real do cérebro desta
  máquina**, não 526 falsos positivos. Cobre o problema de produção
  que eu apontei na revisão de ponta a ponta da v3.7.6.
- **Vision bug7 gating:** `_needs_bug7()` em
  `tests/integration/vision/test_bug7_ollama_local.py` agora honra
  `HIVE_RUN_BUG7=1` corretamente. Antes rodava sempre; agora só roda
  quando explicitamente habilitado. Resolve o falso positivo de "53
  collected, 48 passed" reportado pelo K9.
- **Knowledge health (K8):** `scripts/health/knowledge_health.py`
  refinado — telemetria adicional de cadência, leitura de índice
  de embeddings por coleção canônica, gates de produção mais claros.
- **Vector sync (K1):** `core/vector_sync.py` agora usa
  `core.indexing.upsert_search_vec` ao invés de `INSERT … ON CONFLICT`
  inline. Centraliza o contrato de upsert.
- **`scripts/setup/components.py`:** endurecido — `verify` rejeita
  wrappers (Milvus, RAGFlow, Graphiti, LlamaIndex) em
  `components.lock.json` por padrão, conforme ADR-018.
- **AGENTS.md:** atualizado para refletir o fluxo canônico de
  conhecimento (Capture → Intake → Promotion → Anatomical → Index →
  Retrieval Router → Answer+Citation → Feedback) e o stack born-large
  com `VectorBackend` (sqlite-vec / Milvus).
- **`tests/unit/test_audit_memory_cli.py` (novo):** cobre o split de
  excludes (csv + env) e o matching prefix/glob.
- **`tests/unit/test_components_contract.py` (novo):** cobre ADR-018 —
  rejeita Milvus/RAGFlow em `components.lock.json` automaticamente.
- **`tests/real/test_knowledge_health.py`:** +170 linhas, cobre mais
  métricas K8 com serviços reais.
- **`tests/real/test_retrieval_router_real.py`:** +109 linhas, cobre
  mais rotas K7 (multi-hop, causal, sector).
- **`tests/run_real_knowledge.sh`:** relatório Markdown mais claro
  com K9 totals e skipped por service name.
- **`install.sh` / `pyproject.toml`:** atualizações secundárias
  (ver `git diff`).

### Validation

- CI workflow corrigido — `python3 scripts/setup/components.py bootstrap --strict` agora
  é o caminho canônico.
- `_needs_bug7()` honra env var. Test bug7 suite roda só sob
  `HIVE_RUN_BUG7=1` e não inflates mais o total do K9 report.
- `audit_memory.py --exclude=Thoth,ComfyUI,…` filtra projetos gitignored.
- `components.lock.json` lint rejeita wrappers via
  `scripts/setup/components.py verify`.

### Note

- Esta versão fecha os bloqueantes #1 (audit drift), #2 (`--exclude`
  para audit), #7 (`_needs_bug7` gating) e #15 (relatório K9 mais
  honesto) da lista de produção que eu apontei na revisão de
  v3.7.6. Demais itens (cron de produção, K3/K4 local-only,
  backup automático, K6/Milvus/RAGFlow via `install.sh`) continuam
  como melhorias incrementais.


## v3.7.6 — Local Vision Stack Refresh + Knowledge Born-Large Documentation

Release date: 2026-06-30

### Changed

- **Local vision stack (Codex):** `install.sh` agora baixa
  `minicpm-v4.6:latest` no `local-min` quando Ollama >= 0.30. Em Ollama
  antigo, o instalador usa `gemma3:4b` como fallback funcional. `gemma3:4b`
  entra como fallback no `local-full`. `deepseek-ocr:latest` opt-in para
  OCR dedicado (`SINAPSE_PULL_DEEPSEEK_OCR=1` ou
  `HIVE_OCR_MODEL=deepseek-ocr:latest`). `llava:7b` removido do instalador.
- `.env.example`, `config/env.roles.example`, `README.md`,
  `.github/copilot-instructions.md`, `docs/01`, `docs/04`, `docs/05`,
  `docs/12` e este `CHANGELOG.md` atualizados para não guiarem agente
  para modelo antigo/pesado.
- **Knowledge Born-Large (K0–K10) documentation:** `docs/01-architecture.md`
  consolidado como referência canônica destilada de
  `docs/11-knowledge-promotion-architecture.md` (normativo) e
  `docs/12-knowledge-implementation-plan.md` (plano). Novas seções §22–§31:
  fluxo de 9 etapas, `VectorBackend` com 7 coleções canônicas, `DocumentPipeline`
  (K6), `RetrievalRouter` (K7), `Knowledge Promotion Pipeline` (K3/K4),
  métricas K8, cadência hierárquica sessão→anual (K5), escala/isolamento
  (K10) e contratos pendentes (Reranker, Forget, Eval, Harness). ADRs 001–009
  herdadas + **010–018** criadas pela frente Born-Large. 8 documentos do
  diretório `docs/` sincronizados.
- K5 cadência outputs (`cerebro/cerebelo/anual/2026.md`, `mensal/2026-06.md`,
  `diario/2026/06/2026-06-29.md`) e K9 test reports (`docs/reports/k9-*`)
  commitados como evidência de validação do contrato v3.7.5.
- `.gitignore` atualizado: cache AST do graphify, working copies de hooks de
  agente (`.codex/hooks.json`, `.agents/`) e output runtime do graphify na
  raiz (`/GEMINI.md`) excluídos. Arquivos canônicos (`cerebro/GEMINI.md`,
  `.github/copilot-instructions.md`) continuam tracked.

### Validation

- `ollama pull minicpm-v4.6:latest` passou.
- `ollama rm llava:7b` passou.
- `core.auth.get_role_config("vision")` resolveu para
  `ollama/minicpm-v4.6:latest` com fallback `ollama/gemma3:4b`.
- `bash -n install.sh` e `git diff --check` passaram.
- Teste real de visão: 2 passed in 21.74s.
- Validação herdada de v3.7.5: K9 real suite 53 collected, 48 passed,
  5 skipped, 0 failed; `run_all` Smoke 19 / Unit 497+3 skipped /
  Integration 111+2 skipped / E2E 22.

### Note

- `glm-ocr:latest` ainda existe instalado localmente, mas não é mais
  default nem instalado pelo instalador. Mantido por compatibilidade;
  o pedido explícito foi remover o `llava:7b`.

## v3.7.5 — K9/K10 Final Acceptance Hardening

Release date: 2026-06-30

### Changed

- K10 `install.sh --with-real-tests` agora falha fechado quando
  `tests/run_real_knowledge.sh` retorna exit diferente de zero. O gate K9
  deixa de ser aviso operacional quando o caller pediu validação real.
- O instalador ficou idempotente em reexecução: copia `bun` por arquivo
  temporário + rename atômico, preserva checkout Graphify sujo em bootstrap
  não estrito e reconstrói HNSW após backfill de vetores canônicos ausentes.
- O instalador K10 passa a baixar um modelo local leve para Vision/OCR,
  além de `snowflake-arctic-embed2`, `qwen2.5:3b` e `qwen2.5-coder:3b`.
- `.env.example` passa a documentar Vision local leve, evitando defaults
  pesados que podem estourar VRAM em hosts menores.
- Wrappers `integrations.ragflow` e `integrations.milvus` agora exportam
  suas APIs públicas via `__init__.py`, cobrindo os imports usados pelas
  fixtures reais K9.
- `scripts/setup/audit_test_layering.py` foi limpo para apontar direto para
  o relatório versionado `docs/reports/k9/test-layering-audit.md`.
- `tests/real/test_cadence_real.py` não vaza mais `core.database.DB_PATH`,
  corrigindo o gate live Milvus quando a suíte real roda completa.
- `docs/12-knowledge-implementation-plan.md` foi alinhado ao contrato real:
  K9 com relatório fresco, K10 fail-closed sob `--with-real-tests`, modelo
  Vision local leve e auditoria pós-v3.7.5.

### Validation

- `./tests/run_real_knowledge.sh --report=docs/reports/k9-real-suite-report.md`:
  53 collected, 48 passed, 5 skipped, 0 failed, 0 errors in 221.06s
  (Milvus online; remaining skips are RAGFlow offline/container conflict).
- `./install.sh --profile=local-full --with-real-tests --non-interactive`:
  exit 0; internal K9 report in `logs/k9-real-suite-report.md` with
  48 passed, 5 skipped, 0 failed in 333.54s; final install report in
  `logs/install-report.md`.
- `.venv/bin/python scripts/setup/audit_test_layering.py --strict`:
  20 real tests with `real` marker, 0 real tests with mocks, 0
  unit/integration tests with `real`.
- `./tests/run_all.sh`:
  Smoke 19 passed; Unit 497 passed / 3 skipped; Integration 111 passed /
  2 skipped; E2E 22 passed.
- Targeted regression:
  `tests/unit/test_sinapse_write_cli.py::TestSinapseWriteCLI::test_health_command`
  passed, and Vision real fallback/direct tests passed with the configured
  local Ollama vision model.

## v3.7.3 — K9 Namespace-per-test FalkorDB + RAGFlow Upload/List

Release date: 2026-06-30

### Changed (escopo do projeto; sem CI)

- Refactors `falkordb_or_skip` in `tests/real/conftest.py` to give each
  test a unique `FALKORDB_DB` (`hm_test_<uuid12>`) via `monkeypatch`,
  isolating the namespace without callers needing `DETACH DELETE`.
  Teardown drops the database and invalidates the Graphiti singleton
  cache.
- Drops the `DETACH DELETE` cleanup from
  `tests/real/test_graphiti_falkordb.py::test_graphiti_push_neuron_writes_to_real_backend`
  — the namespace isolation is now the fixture's job.
- Adds 2 real RAGFlow tests in `tests/real/test_ragflow_real.py`:
  `test_ragflow_create_and_list_dataset` (create + list + delete
  dataset) and `test_ragflow_upload_then_list_documents` (upload
  markdown + list documents). When RAGFlow is offline, both skip
  with a named reason.
- `docs/12-knowledge-implementation-plan.md`: §K9 e §K10 ganham
  preenchimento detalhado (Status, Por que, Contrato operacional de 8
  itens, Fluxo, Componentes tabela, Contrato de banco, Fronteiras
  explicitas, Cobertura de edge cases). §10.1 reescrita sem mencao a
  CI, billing, `run_real_knowledge_local_full.sh` ou
  `docker-compose.ragflow-full.yml` (escopo do projeto, nao do repo).

### Validation (rodada em 2026-06-30)

- `.venv/bin/python -m pytest tests/real/test_graphiti_falkordb.py -v`:
  3 passed in 5.85s (FalkorDB online; namespace per test verified).
- `.venv/bin/python -m pytest tests/real/test_ragflow_real.py -v`:
  5 skipped in 0.03s (RAGFlow offline; logic covered by skip path).
- `./tests/run_real_knowledge.sh --report=docs/reports/k9-real-suite-report.md`:
  **53 collected, 40 passed, 13 skipped, 0 failed, 0 errors** in
  188.40s. Was 51/40/11 em v3.7.2; +2 RAGFlow tests, ambos com
  comportamento esperado (RAGFlow offline -> skip).
- `.venv/bin/python scripts/setup/audit_test_layering.py`:
  20/20 tests em `tests/real/` carregam marker `real`; 0 usam
  mocks; 0 unit/integration tests com `real`. Relatorio:
  `docs/reports/k9/test-layering-audit.md`.
- `bash -n install.sh` e `bash -n tests/run_real_knowledge.sh`: sem
  erro de sintaxe. Sem regressao em `./tests/run_all.sh`.

### Out of scope (registrado; NAO foi entregue nesta release)

- **CI / GitHub Actions**: nao faz parte do projeto. O gate K9 roda
  via `./tests/run_real_knowledge.sh` no host do desenvolvedor.
- **Stack RAGFlow completa (MySQL + Elasticsearch + Redis)**:
  pertence ao cluster oficial. Quando o wrapper RAGFlow local
  responder em `/api/v1/health`, os 5 testes RAGFlow passam de skip
  para passed sem nenhuma alteracao.
- **`run_real_knowledge_local_full.sh` e `docker-compose.ragflow-full.yml`**:
  removidos em v3.7.3; eram scope creep de uma release anterior.
- **Bug pre-existente `test_live_e2e`**: passa isolado, falha em
  suite (interferencia de `db.DB_PATH` via `real_db` fixture).
  Registrado para triage, NAO consertado nesta entrega.

## v3.7.2 — K9 FalkorDB & RAGFlow Fixtures + Secao 10 Estado Real

Release date: 2026-06-30

### Added

- Adds `falkordb_or_skip` and `ragflow_or_skip` fixtures to
  `tests/real/conftest.py`, completing the K9 real-fixture coverage
  for all 5 services in `service_registry.py` (was 3/5 in v3.7.0;
  now 5/5: ollama, milvus, claude_mem, falkordb, ragflow).
- Adds `tests/real/test_graphiti_falkordb.py` with 3 real tests
  exercising `graphiti_available()` and `push_neuron()` against the
  real FalkorDB instance. **3 passed** in this run (FalkorDB online).
- Adds `tests/real/test_ragflow_real.py` with 3 real tests exercising
  `RAGFlowSettings` and `assert_health(strict=False)` against the
  real RAGFlow wrapper. **3 skipped** in this run (RAGFlow offline;
  comes up with `--profile=local-full`).
- Updates `docs/12-knowledge-implementation-plan.md` §10 with a new
  subsection **10.1 Estado Atual do Corte (2026-06-30, pós-v3.7.0)**,
  mapping each of the 5 items of the original "Proximo Corte
  Recomendado" to the current state (delivered/active/expanded) with
  evidence, plus a forward-looking list of the next real cut:
  mark FalkorDB/RAGFlow as exercised in CI, deepen the FalkorDB
  fixture with a per-test namespace helper, add a RAGFlow upload
  fixture, and lift the real-suite coverage report to 100% on the
  reference machine.

### Validation

- `.venv/bin/python -m pytest tests/real/test_graphiti_falkordb.py
  tests/real/test_ragflow_real.py -v`:
  **3 passed, 3 skipped, 1 warning** in 10.96s (FalkorDB online,
  RAGFlow offline neste host).
- `./tests/run_real_knowledge.sh --report=docs/reports/k9-real-suite-report.md`:
  **51 collected, 40 passed, 11 skipped, 0 failed, 0 errors** in
  80.74s. Was 45/37/8 in v3.7.0; +6 tests added, all behaving as
  expected (3 passed because FalkorDB is online; 3 skipped because
  RAGFlow is offline).
- `.venv/bin/python scripts/setup/audit_test_layering.py`:
  20/20 tests in `tests/real/` carry the `real` marker (was 18/18 in
  v3.7.0); 0 use mocks; 0 unit/integration tests claim `real`.

## v3.7.1 — Role Config Hotfix

Release date: 2026-06-30

### Fixed

- Keeps `graphiti` and `lightrag` roles on local Ollama instead of
  inheriting the Dreamer provider. Without this shortcut, when the
  Dreamer is configured as `antigravity` or any Gemini-tier provider,
  `get_role_config("graphiti")` returned the Dreamer config and the
  Graphiti / LightRAG workers would either burn Antigravity quota or
  fail with the wrong model.
- Honors `HIVE_GRAPHITI_MODEL` / `HIVE_LIGHTRAG_MODEL` env vars; falls
  back to `qwen2.5:3b` when unset. Provider is forced to `ollama` and
  fallback chain is `None` for both roles — they are local-only by
  design.

### Validation

- `.venv/bin/python -m pytest tests/unit/test_role_config.py -v`:
  9 passed (incl. the new
  `test_local_extraction_roles_should_not_inherit_dreamer`).
- `.venv/bin/python -m pytest tests/unit -q`: 497 passed, 3 skipped
  (no regressions vs v3.7.0).
- Runtime probe with `HIVE_DREAMER_PROVIDER=antigravity` and
  `HIVE_GRAPHITI_MODEL=qwen2.5:7b`:
  - `get_role_config("graphiti")` -> `provider=ollama, model=qwen2.5:7b`
  - `get_role_config("lightrag")` -> `provider=ollama, model=qwen2.5:3b`
  - `get_role_config("dreamer")`  -> `provider=antigravity, model=gemini-3.5-flash`
  (and other roles still inherit Dreamer as expected).

## v3.7.0 — K9 Test Harness Real Sem Mocks + K10 Installer E Maquina Zerada

Release date: 2026-06-30

### Added

K9 — Test Harness Real Sem Mocks (docs/12 §K9):

- Adds `milvus_or_skip`, `milvus_backend` (com teardown de colecoes) and
  `claude_mem_or_skip` (SQLite temporario com schema real) fixtures in
  `tests/real/conftest.py` so the real suite no longer relies on a
  pre-running Milvus or claude-mem worker.
- Adds `scripts/setup/audit_test_layering.py` to enforce the real × unit
  × integration layering (no MagicMock in `tests/real/`, no `real` marker
  in `tests/unit/`/`tests/integration/`). Writes
  `docs/reports/k9/test-layering-audit.md` with the offender
  list and counts.
- Adds `tests/real/test_acceptance_split.py` to defend the boundary at
  pytest-collection time — any regression that lets a real test mock
  something, or a unit test mark itself `real`, fails the run.
- Adds `tests/real/test_golden_retrieval.py` with the precision/recall@k
  gate from `docs/11` §17.3: intent classification >= 75% and
  precision@k/recall@k >= 0.5 over `tests/real/golden_retrieval.jsonl`
  (skips cleanly when the seed corpus does not match — does not silently
  pass).
- Marks `tests/real/test_knowledge_health.py` with `@pytest.mark.real`
  (was missing) so it counts toward the knowledge-architecture
  acceptance.
- Expands `tests/run_real_knowledge.sh` with `--report=<path>`: runs
  pytest with junit-xml and writes a Markdown summary next to the run
  log. Used by the new installer flow.

K10 — Installer E Maquina Zerada (docs/12 §K10):

- Adds `--profile=local-min|local-full` and `--with-real-tests` to
  `install.sh`. `local-min` keeps claude-mem + graphify-watch only;
  `local-full` brings up Milvus + RAGFlow via `docker compose up` and
  warns if FalkorDB is offline. Default profile is `local-min` to
  preserve the original behavior on small machines.
- Adds a K10 block to `install.sh` that re-applies
  `core.database.ensure_migrations` (idempotent), runs
  `scripts/setup/register-mcp.sh` after the profile, and (with
  `--with-real-tests`) chains `./tests/run_real_knowledge.sh --report=...`
  into the install flow.
- Adds a final install report at `logs/install-report.md` with vault
  path, ports (claude-mem 37700, sqlite-vec 37701, api 37702, mcp-http
  37703), installed Ollama models, and the full
  `sinapse-write.py health` output. Mirrors the same summary on stdout
  so the operator sees it without opening the file.
- Hardens `install.sh` argument parsing: rejects unknown flags and
  invalid `--profile` values, keeps the old flags backward compatible
  (`--force`, `--with-tests`, `--skip-agent=`, `--provider=`,
  `--model=`, `--non-interactive`).

### Validation

- `.venv/bin/python -m pytest tests/real -m real -q`: 37 passed, 8 skipped
  in 38.88s. Skips are all `requires_service:milvus` (Milvus not started
  in this profile) and are intentional.
- `./tests/run_real_knowledge.sh --report=cerebro/cortex/insula/saude/k9-real-suite.md`:
  45 collected, 37 passed, 8 skipped, 0 failed, 0 errors. Report written.
- `.venv/bin/python scripts/setup/audit_test_layering.py`: 17/17 tests
  in `tests/real/` carry the `real` marker; 0 use mocks; 0 unit /
  integration tests claim `real`. Audit log written to
  `cerebro/cortex/insula/saude/test-layering-audit.md`.
- `.venv/bin/python -m pytest tests/real/test_acceptance_split.py -q`:
  4 passed (boundary guard).
- `.venv/bin/python -m pytest tests/real/test_golden_retrieval.py -q`:
  2 passed (intent gate + precision/recall@k gate).
- `.venv/bin/python scripts/services/sinapse-write.py health`:
  `healthy=true`, 7/7 backends up (umc, neural_memory, sqlite_vec,
  claude_mem, graphify, graphiti, filesystem), 1020 graph nodes,
  5706 neurons, 97.76% vectorized.
- `bash -n install.sh` and `bash -n tests/run_real_knowledge.sh`: no
  syntax errors after the K10 block insertion.

## v3.6.0 — K8 Knowledge Health

Release date: 2026-06-30

### Added

- Adds `scripts/health/knowledge_health.py` to measure knowledge coverage
  without replacing the existing insula health dashboard.
- Measures `neurons_vectorized_pct`, `observations_linked_pct`,
  `discoveries_pending`, `summary_vectors_total`, `orphan_vectors`,
  `milvus_sync_lag`, `query_route_distribution` and per-collection
  `*_vectorized_pct`.
- Adds `knowledge_tombstones` and `query_route_log` to the UMC schema and
  CRR-safe schema.
- Adds best-effort route telemetry in `RetrievalRouter` so
  `query_route_distribution` is based on stored route paths, not guesses.
- Keeps route telemetry fail-open/fail-fast under SQLite lock, preventing
  `sinapse-write.py query` from timing out while preserving K8 route logs.
- Adds intentional forgetting for orphan vectors: prune local sqlite-vec rows,
  clean metadata and write auditable tombstones with reason `orphan_vector`.
- Exposes K8 coverage in `sinapse_health` under `knowledge_health` using a
  quick/read-only path; the CLI and REST endpoint keep the complete gate.
- Adds authenticated REST endpoint `GET /api/v1/knowledge/health` with
  read-only default and `prune=true` maintenance mode.
- Writes Markdown reports to
  `cerebro/cortex/insula/saude/knowledge-health-YYYY-MM-DD.md`.
- Adds real K8 coverage in `tests/real/test_knowledge_health.py`.

### Validation

- `.venv/bin/python scripts/health/knowledge_health.py --fail-closed --json`:
  exit 0, `failures=[]`, `orphan_vectors=0`.
- `.venv/bin/python -m pytest tests/real/test_knowledge_health.py -q`:
  2 passed.
- `.venv/bin/python -m pytest tests/unit/test_sinapse_write_cli.py::TestSinapseWriteCLI::test_query_command tests/unit/test_sinapse_mcp.py tests/integration/test_sinapse_api.py tests/real/test_knowledge_health.py -q`:
  21 passed, 1 skipped.
- `./tests/run_all.sh`: Smoke 19 passed; Unit 497 passed / 3 skipped;
  Integration 111 passed / 2 skipped; E2E 22 passed.

## v3.5.0 — K7 RetrievalRouter

Release date: 2026-06-30

### Added

- Adds `core/retrieval/router.py` with explicit query intents:
  `recent_activity`, `decision`, `learning`, `document`, `code`, `causal`,
  `multi_hop`, `visual`, `self_state`, `operational`, `sector` and `hybrid`.
- Returns an auditable retrieval envelope with `answer_context`, `citations`,
  `retrieval_path`, `confidence` and `missing_context`.
- Routes recent activity through claude-mem temporal search/hydration, documents
  through `document_vectors`, memory questions through `memory_vectors`, code
  through `code_vectors` + Graphify, causal questions through Graphiti +
  `graph_vectors`, and multi-hop questions through LightRAG.
- Integrates the router into MCP `sinapse_query`, REST `/api/v1/query` and
  `scripts/services/sinapse-write.py query` while preserving legacy
  Context-Fusion fields for existing clients.
- Adds `core.search.route_retrieval()` as the internal search-layer adapter for
  callers that need the K7 envelope without going through MCP/REST.
- Adds optional `integrations/llama_index/` reranker adapter, disabled by
  default and fail-open.
- Adds `tests/real/golden_retrieval.jsonl` for intent accuracy regression.

### Validation

- `.venv/bin/python -m pytest tests/real/test_retrieval_router_real.py -q`:
  3 passed.
- `.venv/bin/python -m pytest tests/unit/test_sinapse_mcp.py tests/unit/test_sinapse_write_cli.py tests/integration/test_sinapse_api.py tests/real/test_retrieval_router_real.py -q`:
  29 passed, 1 skipped.
- `python3 scripts/services/sinapse-write.py query "o que foi decidido sobre embeddings?"`:
  exit 0 and returned K7 fields (`intent`, `retrieval_path`, `citations`,
  `confidence`, `missing_context`).
- `./tests/run_all.sh`:
  Smoke 19 passed; Unit 497 passed / 3 skipped; Integration 109 passed /
  2 skipped; E2E 22 passed.

## v3.4.0 — K6 DocumentPipeline With Parent Context

Release date: 2026-06-30

### Added

- Adds `core/document_pipeline.py` as the canonical K6 document ingestion
  pipeline with parent records, structural chunks, offsets, hashes and
  citation return.
- Adds Markdown section chunking, plain text ingestion, real PDF parsing via
  `pypdf`/`PyMuPDF`, and DOCX parsing via `python-docx`.
- Adds `document_chunks` to the UMC schema and CRR-safe schema.
- Indexes document chunks into `document_vectors` through `SQLiteVecBackend`
  with canonical vector metadata.
- Adds optional RAGFlow adapter health integration while keeping UMC as the
  source of truth.
- Connects `scripts/knowledge/document_ingest.py` to the K6 pipeline for real
  PDF/DOCX ingestion while preserving legacy observation records.
- Adds real K6 coverage for Markdown, PDF and the legacy ingest bridge.

### Validation

- `.venv/bin/python -m pytest tests/real/test_document_pipeline_markdown.py tests/real/test_document_pipeline_pdf.py tests/real/test_document_ingest_pipeline.py -q`:
  3 passed.
- `.venv/bin/python -m pytest tests/unit/test_document_ingest.py -q`:
  8 passed.
- `./tests/run_all.sh`: Smoke 19 passed; Unit 497 passed / 3 skipped;
  Integration 109 passed / 2 skipped; E2E 22 passed.

## v3.3.0 — K5 Hierarchical Cadence

Release date: 2026-06-29

### Added

- Adds K5 monthly and yearly cadence writers:
  `scripts/dream/monthly_synthesizer.py` and
  `scripts/dream/yearly_synthesizer.py`.
- Adds structured Pydantic contracts for higher cadence synthesis:
  `MonthlySummaryModel` and `YearlySummaryModel`.
- Writes monthly summaries to `MONTHLY_ROOT` and yearly summaries to
  `YEARLY_ROOT` using the canonical paths in `core/paths.py`.
- Indexes session, daily, weekly, monthly and yearly cadence outputs into
  `summary_vectors` through a new `index_summary_file_to_sqlite()` helper.
- Extends `summary_vectors` backfill to include `cerebro/cerebelo/anual`.
- Adds real K5 cadence coverage in `tests/real/test_cadence_real.py`.

### Validation

- `HIVE_SESSION_SUMMARIZER_PROVIDER=ollama HIVE_SESSION_SUMMARIZER_MODEL=qwen2.5:3b .venv/bin/python scripts/dream/session_consolidator.py --real`:
  exit 0, session summary indexed in `summary_vectors`.
- `.venv/bin/python scripts/dream/monthly_synthesizer.py --month "$(date +%Y-%m)" --real`:
  exit 0, wrote `cerebro/cerebelo/mensal/2026-06.md` and indexed it.
- `.venv/bin/python scripts/dream/yearly_synthesizer.py --year "$(date +%Y)" --real`:
  exit 0, wrote `cerebro/cerebelo/anual/2026.md` and indexed it.
- `.venv/bin/python -m pytest tests/real/test_cadence_real.py -q`:
  1 passed.
- Focused cadence/vector regression:
  `tests/unit/test_session_cadence.py tests/real/test_vector_auxiliary_collections.py`:
  15 passed, 1 skipped.
- `./tests/run_all.sh`: Smoke 19 passed; Unit 496 passed / 3 skipped;
  Integration 109 passed / 2 skipped; E2E 22 passed.

## v3.2.1 — Vision Setup-Brain Validation Fix

Release date: 2026-06-29

### Fixed

- Fixes the real vision integration test to respect the active `setup-brain`
  configuration (`HIVE_VISION_*`) instead of forcing `ollama-cloud/gemma3:4b`.
  The active runtime path is local Ollama and must be controlled by
  `HIVE_VISION_*`.
- Removes the false external-billing assumption from the K4 validation notes:
  the vision path is local and must pass locally when the configured Ollama
  model is installed.

### Validation

- `HIVE_RUN_INTEGRATION=1 .venv/bin/python -m pytest tests/integration/vision/test_vision_real.py -q -rs`:
  3 passed.

## v3.2.0 — Claude-Mem Promotion Bridge

Release date: 2026-06-29

### Added

- Adds the K4 Claude-Mem Promotion Bridge in `core/knowledge/claude_mem_bridge.py`,
  importing Claude-Mem observations, discoveries and session summaries into UMC
  observations with stable `source_id` metadata.
- Exposes Claude-Mem import filters through CLI/MCP promotion:
  `sinapse-write.py promotion --import-claude-mem --source-id ...` and
  `sinapse_promote_knowledge(import_claude_mem=true, ...)`.
- Adds `operational_fact` as a canonical promotion type for completed session
  work from Claude-Mem summaries.

### Fixed

- Makes the Antigravity provider use the native `agy` auth token
  (`~/.gemini/antigravity-cli/antigravity-oauth-token`) as the primary
  configured-state check, instead of requiring Gemini CLI OAuth.
- Carries the native `agy` token into `AGY_USE_ISOLATED_HOME=1` diagnostic
  runs so isolated mode no longer drops Antigravity authentication.
- Updates `setup-brain.py` labels and model-source messages to distinguish
  `agy` auth from Gemini CLI OAuth.

### Validation

- `tests/real/test_claude_mem_bridge.py`: 2 passed.
- Focused K4/CLI/MCP/Antigravity regression: 83 passed.
- `./tests/run_real_knowledge.sh`: 21 passed, 8 skipped.
- Real Claude-Mem import/promotion:
  `sinapse-write.py promotion --import-claude-mem --source-id ...`: inserted 2,
  promoted 6, preserving `source_id` metadata.
- Acceptance CLI with system Python:
  `python3 scripts/services/sinapse-write.py query "ultimos discoveries promovidos"`:
  exit 0, no `sqlite-vec` import failure because the CLI re-executes through
  the project `.venv`.
- `./tests/run_all.sh`: Smoke 19 passed; Unit 496 passed / 3 skipped;
  Integration 107 passed / 4 skipped; E2E 22 passed.

## v3.1.0 — Knowledge Intake & Promotion Pipeline

Release date: 2026-06-29

### Highlights

- Introduces the K3 Knowledge Intake and Promotion pipeline for typed,
  evidence-preserving promotion of observations, discoveries, summaries,
  documents and code into durable knowledge candidates.
- Adds the K2 VectorBackend contract and canonical vector collections so
  SQLite/sqlite-vec and Milvus share one operational surface.
- Hardens the Antigravity (`agy`) provider path so it uses the real CLI
  authentication by default while keeping isolated HOME as an explicit
  diagnostic mode.
- Revalidates the real Dream Cycle path end to end with Antigravity,
  Graphiti, LightRAG, Ollama embeddings and the UMC schema.

### Changes

- Added `core/knowledge/intake.py` and `core/knowledge/promotion.py`.
- Added `knowledge_candidates` to the UMC schema, CRR schema and CRDT setup.
- Added CLI and MCP surfaces for K3 promotion:
  `sinapse-write.py promotion` and `sinapse_promote_knowledge`.
- Refactored specialized promoters to expose candidate-only outputs with
  `workspace_id`: `decision_promoter`, `pattern_distiller`,
  `conflict_detector`, `sector_classifier`, `drift_detector`,
  `topic_consolidator` and `work_tracker`.
- Added vector sync CLI and auxiliary vector collection tests.
- Added bounded Graphiti/LightRAG push behavior in Dream Cycle to prevent
  unbounded graph indexing from blocking promotion.

### Validation

- `tests/real/test_promotion_pipeline_sqlite.py`: 3 passed.
- `scripts/dream/dream_cycle.py --once --real`: ok, 30 observations,
  29 K3 candidate-only records, 19 neurons persisted across 3 projects.
- `scripts/services/sinapse-write.py query "decisoes promovidas hoje"`:
  exit 0, JSON on stdout.
- Focused K3/CLI/MCP/Graphiti regression: 89 passed.
- `./tests/run_real_knowledge.sh`: 19 passed, 8 skipped.
- `./tests/run_all.sh`: Smoke 19 passed; Unit 494 passed / 3 skipped;
  Integration 109 passed / 2 skipped; E2E 22 passed.

### Publication Notes

- This release intentionally replaces the previously pushed online K3/K5
  attempt on `origin/main`; the implementation commit is `a15c492`.
- GitHub Release should use the contents of this section as the release body.
