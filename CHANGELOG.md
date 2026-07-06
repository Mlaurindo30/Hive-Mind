# Changelog

## v3.10.0 — Model Gateway + Unified Provider Routing

Release date: 2026-07-06

The Model Gateway becomes the canonical model execution layer. Legacy
`HIVE_{ROLE}_PROVIDER/MODEL` configuration is consumed through
`ModelRegistry.from_combined_config()`, so the setup-brain flow keeps
working unchanged while `config/model-gateway.yaml` becomes an
override/capabilities layer instead of a mandatory duplicated source.

### Added

- Model Gateway as the canonical model execution layer, with a Capability
  Registry and combined legacy/provider/YAML resolution.
- `MODEL_GATEWAY_MODE=auto/on/off`: `auto` tries the gateway and falls back
  to the legacy path; `on` makes the gateway mandatory (never falls back);
  `off` disables it (deprecated).
- `HIVE_FORCE_LEGACY_LLM` as an emergency bypass that prevails over MODE.
- Provider-to-adapter mapping for all known providers, with adapters for
  OpenAI-compatible, LM Studio, llama.cpp, vLLM, SGLang and LiteLLM proxy.
- Model gateway telemetry, health visibility and benchmark CLI.
- Explicit `provider_skipped_due_to_capability` telemetry (closes R6.5).
- Canonical `no_vision_capable_provider` error (closes R8.3).
- `install.sh` now auto-applies the model gateway env block.

### Changed

- Unsupported providers never execute an adapter (closes EC-3).
- `config/model-gateway.yaml` is now override/capabilities only; the
  setup-brain `HIVE_{ROLE}_PROVIDER/MODEL` flow remains the primary source.

### Deprecated

- `MODEL_GATEWAY_ENABLED` kept only as a deprecated shim; use
  `MODEL_GATEWAY_MODE`.

### Fixed

- Claude Mem bridge test isolation: a closed in-memory connection leaked
  from `tests/unit/test_llm_fallback.py` into
  `tests/real/test_claude_mem_bridge.py`; the `real_db` fixture now always
  hands out fresh connections.
- Real knowledge/K5 cadence validation stabilized: subprocess timeouts for
  the `--real` synthesizers raised to 600s and `pytest.mark.timeout`
  markers added so a global `--timeout=300` cannot kill tests whose
  internal subprocess ceiling is legitimately higher.

### Verified

Real OpenAI-compatible backend verified through Ollama. Full battery:
`compileall` exit 0 · `tests/model_gateway/` 50/50 ·
`tests/real/test_claude_mem_bridge.py` isolated and after
`test_llm_fallback.py` · `tests/unit/` 723 passed/3 skipped ·
`tests/integration/` 98 passed/12 skipped · `tests/e2e/` 31 passed ·
`tests/real/` 92 passed/20 skipped (no timeouts) · smoke 19/19 ·
`tests/run_real_knowledge.sh` exit 0.

## v3.9.2 — Redactor: fully mask generic api_key/token/secret values

Release date: 2026-07-04

The v3.9.1 post-audit evidence package flagged a fragile redaction case:
`api_key=abcdef0123456789` left the alphabetic prefix `abcdef` visible and
mislabeled the trailing digits `[REDACTED:phone]`. It did not violate the
spec's literal assertion (the full original value never leaked verbatim),
but was a real risk for future exports/logs.

### Fixed

- `core/redactor.py`: added a rule for generic `key=value` / `key: value`
  secrets — `api_key`, `apikey`, `apiKey`, `API_KEY`, `token`,
  `access_token`, `secret`, `client_secret` — placed before the phone-number
  matcher so the entire value is masked, never partially. The key name and
  separator are preserved verbatim; only the value becomes
  `[REDACTED:token]`. AWS/Bearer/OpenAI rules are untouched.

### Added

- `tests/unit/test_redactor_generic_api_keys.py` (13 tests) — locks in the
  fix and explicitly guards against regressing AWS/Bearer/OpenAI redaction.

### Verified

`tests/unit/test_redactor.py` 10/10 · `test_redactor_aws_tokens.py` 7/7 ·
new `test_redactor_generic_api_keys.py` 13/13 · full `tests/unit/` suite
632 passed/3 skipped (0 regressions) · `compileall` exit 0.

## v3.9.1 — Post-audit stabilization: close the last four accepted-with-caveats items

Release date: 2026-07-04

The prior stabilization pass (v3.7.6–v3.8.0) closed 49 of 53 spec items and
left four as "accepted with rationale" rather than genuinely done: RTK/Graphify
version drift (R1.4/R9.1), Syncthing (R11.1), the P2P conflict test (R11.3),
and the full `install.sh --with-tests` zero-to-green run (D7). This release
closes all four for real, and along the way surfaces and fixes three
pre-existing regressions that the full test suites had never actually been
run end-to-end to catch.

### Fixed

- **RTK version drift (R1.4)**: `integrations/patches/rtk-umc-logging.patch`
  still reflected the pre-fix, buggy `_log_to_umc` duplication — regenerated
  from the corrected file. `scripts/setup/components.py verify` now exits 0
  with `patch=ok` on all three pinned components.
- **Graphify version drift (R9.1)**: corrected a prior wrong claim.
  The project's actual runtime (the watcher's `python -m graphify`,
  `install.sh`'s `.venv/bin/graphify`) already resolves to `0.8.49`, matching
  `config/components.lock.json`. Only a separate, host-level personal CLI
  tool (`uv tool install graphifyy`, outside repo scope) could lag behind.
  `docs/04-infrastructure.md` rewritten accordingly.
- **`register-mcp.sh --check` exit code**: exited 1 whenever zero agents
  were detected, even in `--check` mode — contradicting its own
  "must exit 0" requirement and the project's zero-to-green-without-an-IDE
  precedent. `--check` is now informational on zero agents.
- **Agent-hook templates never reached a fresh install**: 4 of 7 agent-hook
  directories (`.claude`, `.claude-flow`, `.gemini`, `.hermes`) existed only
  on one machine's live, gitignored vault — never added to the shipped
  `templates/vault/`, and additionally swallowed by unanchored `.gitignore`
  patterns even after being added. Both root causes fixed: the templates are
  now shipped, and `.gitignore` carries scoped negations so tool-state
  directories elsewhere in the tree stay ignored.
- **`tests/integration/test_watcher_graphify_indexing.py`**: hardcoded a
  stale, empty legacy path instead of the real canonical graph-output
  directory the retrieval router actually reads.
- **`tests/unit/test_knowledge_governance.py`**: its test-database fixture
  was missing the `vector_jobs` table added for vectorization queueing,
  silently quarantining every promotion with a database error. Full
  `pytest tests/unit/ -q` had never been run end-to-end since that table was
  added, so this went uncaught.
- **`tests/integration/vision/conftest.py`**: its "vision tests disabled by
  default" collection hook applied the skip marker to every test in the
  whole session, not just its own directory.
- Removed a fourth stray PostScript test artifact (`argparse`, 96k lines)
  from the same accidental-commit batch partially cleaned up previously.

### Added

- Syncthing installed (user-space binary, no root required) — R11.1 closed.
- `tests/real/test_p2p_conflict.py` — drives the real conflict router
  (`scripts/health/audit_memory.py` + `core.database.register_ambiguity`,
  no mocks) against an isolated SQLite file, reproducing the exact
  `.sync-conflict-<date>-<time>-<device>.md` filename Syncthing produces on
  a real collision. Confirms the conflict is registered and the canonical
  neuron is never silently overwritten — R11.3 closed.
- `tests/install/run-clean-install-test-local.sh` — companion to the
  existing Docker zero-to-green harness that injects the current working
  tree (tracked + untracked-but-not-gitignored files) instead of requiring
  a pushed ref, so `install.sh --with-tests` can be validated against local
  branches. Used to close D7 with a real green run in a fresh
  Ubuntu-24.04-with-systemd container (no Hive-Mind, Ollama, or IDE
  pre-installed).

### Verified (same session)

`compileall` exit 0 · smoke 19/19 · unit 619 passed/3 skipped · integration
116 passed/3 skipped · e2e 23 passed · real-knowledge 88 passed/1 skipped ·
K8 gate 99.77% vectorized, 0 orphans · Docker zero-to-green exit 0.

## v3.9.0 — Windows nativo + enforcement multiplataforma (beta)

Release date: 2026-07-02

Agentes no Windows (Claude Code, Cursor, Copilot) rodam no host — uma
instalação presa ao WSL2 fica em outro namespace de filesystem/rede que os
configs MCP deles não alcançam. O `init` do npm agora instala **nativo no
Windows** por padrão, e o enforcement de vault ganhou variantes macOS e
Windows (ambas beta, ainda não validadas em hardware real).

### Added

- **Bootstrap nativo Windows** (`npm hive-sinapse-mind@3.9.0`, `lib/init.js`):
  no win32 o `init` executa o núcleo do install.sh com ferramentas
  multiplataforma — clone, `uv sync --frozen --all-groups`, vault de
  `templates/vault`, `.env` (forçando `sqlite_vec`), registro MCP direto nos
  configs JSON dos agentes do host (`.mcp.json` do projeto p/ Claude Code,
  `~/.cursor/mcp.json`, `~/.codex/mcp.json` com `python.exe` do venv) e
  serviços via supervisor Node (F3). WSL2 vira fallback apenas quando
  `git`/`uv` faltam no host.
- **Enforcement de vault macOS (beta)**: branch Darwin no
  `setup-vault-enforcement.sh` — role account via `sysadminctl`, ACLs
  `chmod +a` herdadas para edição humana, mesmo modelo do Linux.
- **Enforcement de vault Windows nativo (beta)**:
  `scripts/setup/setup-vault-enforcement.ps1` — conta de serviço local,
  `icacls` com quebra de herança (service account F, humano M, others
  negados) e `90-intake` gravável por Authenticated Users. `-Status`/`-Revert`.
- README: matriz de plataformas com coluna de enforcement e nota sobre por
  que Windows nativo é o padrão.

### Fixed

- `setup-vault-enforcement.sh`: `hive-dreamer` não conseguia atravessar o
  caminho até o vault quando o projeto vive sob o HOME do humano (ex.:
  `/home/<user>` 750) — ACLs de travessia execute-only aplicadas ao longo do
  path; `stat` portável Linux/macOS no `--status`.
- **Portabilidade**: removidos os últimos caminhos absolutos de máquina de 5
  arquivos funcionais (benchmark_watcher, copilot-wrapper, crontab template
  com `__PROJECT_ROOT__`, claude-mem-plugins installer, langfuse compose com
  volume relativo) — instalação zero em qualquer máquina sem paths herdados.

> **Beta honesto:** os enforcements macOS/Windows e o bootstrap nativo win32
> foram validados por sintaxe e revisão, não em hardware real — validação em
> máquina física/CI é o próximo passo antes de promovê-los a estável.

## v3.8.0 — Governança de conhecimento proporcional ao risco

Release date: 2026-07-02

Ciclo de vida do conhecimento inspirado no estudo federated-memory
(whitepaper + EXP-001): promoção proporcional ao risco em vez de fila cega
por idade, validade temporal por nota, disciplina epistêmica
(verified × hypothesis) e enforcement físico opcional de escrita no vault.
Suíte real do gate de release: **59/59 verdes** com backends reais
(`logs/governance-real-suite-report.md`); 611 testes unit (42 novos).

### Added

- **Classificação confidence × risk no intake** (`core/knowledge/intake.py`):
  todo `KnowledgeCandidate` nasce com `confidence`
  (`verified` quando a evidência tem artefatos concretos — files/commands/
  source_uri — senão `hypothesis`) e `risk` (`high` para segredos/credenciais
  e operações destrutivas). Declaração explícita em `metadata.governance`
  tem precedência. Determinístico, sem LLM.
- **Política de promoção proporcional ao risco**
  (`core/knowledge/promotion.py`): `verified+low` promove imediato com
  `ttl_review` de 90 dias; `hypothesis` fica `held` e é drenado após 7 dias
  (`promote_held_candidates`); `risk=high` só promove com aprovação explícita
  (`reprocess_quarantine.py --include-high-risk`) — nunca automático.
  Migração de schema idempotente e CRR-safe; kill-switch
  `HIVE_GOVERNANCE_RISK=0` restaura o promote-all.
- **Validade temporal por nota**: `save_decision`/`save_learning` gravam
  `review_date`/`next_review` (+90d) e `confidence` no frontmatter; parâmetro
  `evidence` marca a nota `verified` (exposto nas tools MCP
  `sinapse_save_decision`/`sinapse_save_learning`). Backfill idempotente das
  notas curadas existentes via data de commit git
  (`scripts/maintenance/backfill_review_dates.py`, 230 notas atualizadas).
- **Penalidade de staleness no RetrievalRouter** (`core/retrieval/router.py`):
  itens com `ttl_review`/`next_review` vencido ou `confidence=hypothesis`
  têm o score multiplicado por `HIVE_STALENESS_PENALTY` (default 0.85) e são
  rebaixados — nunca excluídos — com anotação `governance_flags`.
- **Staleness no audit** (`scripts/health/audit_memory.py`): varredura das
  áreas curadas (frontal + cerebelo) listando notas com `next_review` vencido
  e decisões sem `next_review`.
- **Fila de revisão no knowledge health**: `governance_review_queue`
  (held por risco) exposto em `knowledge_health.py`/`sinapse_health`.
- **Enforcement físico de escrita no vault (opt-in)**
  (`scripts/setup/setup-vault-enforcement.sh`, `install.sh
  --with-vault-enforcement`): usuário de sistema dedicado dono de `cerebro/`,
  agentes com escrita só em `cerebro/90-intake/`. Os writers caem para a área
  de intake automaticamente quando a escrita direta é negada
  (`promote_to` no frontmatter para o Dream Cycle rotear). Lição do EXP-001:
  chmod pelo próprio dono não é enforcement — o agente roda como o dono.
- **Contrato epistêmico** (`config/sinapse-agent-prompt.md`): ao salvar
  decisão/learning, passar `evidence` quando a afirmação foi verificada;
  hipótese refutada deve ser corrigida na nota.

### Changed

- `dream_cycle.py` (estágio de intake de candidatos): relatório com
  contadores por classe (`verified_low`, `hypothesis`, `high_risk`).
- Teste real do bridge claude-mem atualizado ao novo contrato: observação
  `change` sem artefatos agora é `held_hypothesis` e o teste exercita o ciclo
  completo hold → drain → promote.

## v3.7.12 — Zero-to-green em máquina virgem + harness de instalação limpa

> **Publicação npm:** pacote `hive-sinapse-mind@3.7.12` publicado em
> 2026-07-02 (registry `npmjs.com`, owner `mlaurindo`, 8 arquivos, 7.6 kB).
> O nome `hive-mind` foi rejeitado por colisão de similaridade com
> `hivemind@0.1.2`; o nome `hive-sinapse-mind` amarra a marca ao produto
> interno (Sinapse Memory) e preserva o binário `hive-mind` no PATH.
> Instalação via `npm i -g hive-sinapse-mind` ou
> `npx hive-sinapse-mind@latest init`.

Release date: 2026-07-02

Release date: 2026-07-02

Instalação limpa comprovada de ponta a ponta: container virgem (Ubuntu 24.04 +
systemd, apenas os pré-requisitos do README — uv, Node 18+, Bun; sem Docker,
Ollama ou IDE) clonando o `main` publicado e rodando
`./install.sh --profile=local-min --with-tests --non-interactive` → exit 0 com
4/4 suítes verdes, API online (auth fail-closed) e serviços ativos.

### Fixed

- **`verify_wrappers` exigia Docker até no `local-min`** e abortava o install
  no passo 2. A validação estática (compose parseável + imagens com digest
  pinado) roda sempre; `docker compose config` só é obrigatório com
  `--require-docker` (perfil `local-full`).
- **Circuit breaker no `OllamaEmbedder`** (`core/database.py`): conexão
  recusada abre o breaker (`EmbedderOffline`) em vez de pagar retry+backoff
  por item — sem Ollama, o `graphify update` gastava ~2.5s × ~800 nós
  (~40 min de install aparentemente travado).
- **Export do Graphify** (patch pinado `graphify-hive-mind.patch`): desliga a
  vetorização no primeiro `EmbedderOffline` com aviso único; o grafo
  estrutural segue completo.
- **`build_hnsw.py`**: preflight do backend de embedding — sem Ollama vira
  skip com aviso (busca semântica degrada para texto) em vez de abortar o
  install; fail-closed mantido quando o endpoint existe e os vetores faltam.
- **`.env` recém-criado herdava `VECTOR_BACKEND=milvus`** do exemplo, causando
  `MilvusException` em MCP/CLI/API sem Docker. Install fresco fora do
  `local-full` força `sqlite_vec`; `.env` pré-existente nunca é alterado.
- **Workers temporais sem plugin claude-mem crash-loopavam** no boot de
  máquinas sem IDE/agente. `install_services.py` só habilita
  `sinapse-claude-mem`/`sinapse-sqlite-vec` com o plugin presente (e desabilita
  instalações antigas órfãs); smoke S0.3 e o capture doctor tratam o caso como
  SKIP explícito.
- **Testes dependentes do ambiente do host**: `test_llm_fallback` pina
  `LLM_PROVIDER` (colidia com fallback quando o primário do host era ollama);
  `test_metrics_endpoint_authenticated` compara `indexes.hnsw` com o estado
  real do disco; testes de `embed_text` skipam sem backend real.

### Added

- **Harness de instalação limpa** (`tests/install/`): Dockerfile de máquina
  virgem (systemd PID1) + `run-clean-install-test.sh`, que clona o repo
  publicado e usa o exit code do installer (`--with-tests`) como gate.
  Reutilizável como gate de release.
- **Testes do circuit breaker** (`tests/unit/test_embedder_circuit_breaker.py`).

## v3.7.11 — Warmup da fusão + telemetria fora do request path

Release date: 2026-07-02

Elimina as duas ressalvas de performance da review da v3.7.10, medidas
em execução real contra a API viva.

### Performance

- **Warmup da Context Fusion no startup** (`sinapse-api.py`): o
  `api_lifespan` dispara uma thread daemon que pré-carrega a ponte de
  fusão (imports, índices HNSW, caches de embedding) com uma query de
  aquecimento. O readiness não é afetado (health em ~8ms pós-restart);
  a primeira query híbrida REST caiu de ~19.5s para ~1.5s — paridade
  com o caminho MCP.
- **`flush_telemetry()` removido do caminho do request**: o
  `BatchSpanProcessor` (`schedule_delay_millis=1`) já exporta spans em
  thread própria, então o `force_flush` por request só bloqueava o
  event loop. Spans verificados chegando ao collector sem ele; o flush
  agora acontece apenas no shutdown do lifespan.

## v3.7.10 — Correções da auditoria E2E REST API

Release date: 2026-07-01

### Fixed

- **REST `/api/v1/query` híbrido**: a API agora injeta `sinapse_query_fn`
  no `RetrievalRouter` usando a ponte lazy para `sinapse_memory._query_vault_knowledge`,
  preservando fallback sem 500 quando a fusão estiver indisponível.
- **K10 workspace na busca REST**: `POST /api/v1/query` passa
  `workspace_id=current_workspace_id()` ao router, mantendo isolamento
  multi-tenant quando `HIVE_MULTI_TENANT_ENABLED=true`.
- **Systemd crash-loop tolerance**: templates do instalador usam
  `StartLimitIntervalSec=300`, `StartLimitBurst=5` e `RestartSec=15`
  nos serviços críticos para evitar desistência permanente após rajadas curtas.

### Added

- **REST OTEL spans**: middleware HTTP emite spans `api.<path>` com
  `method`, `path`, `status_code` e `workspace_id`, e retorna `X-Trace-Id`
  sem registrar token, body ou conteúdo de observações.
- **`hive-otel-collector.service` no instalador**: o collector local OTLP
  passa a ter unit canônica e restart policy igual aos serviços críticos.

### Security

- **`GET /api/v1/workspaces` condicional**: permanece aberto em loopback
  para operação local, mas exige Bearer auth quando `HIVE_MIND_API_HOST`
  aponta para bind não-loopback.

## v3.7.9 — K10 Multi-Workspace Runtime + OTEL Tracing Ativo

Release date: 2026-07-01

Resolve os 3 itens finais da review de produção da v3.7.6 que ainda
dependiam de trabalho manual: K10 multi-workspace, tracing OTEL, e
drenagem programada de quarentena.

### Added

- **K10 — `core/workspace.py` (F4.7)**: modulo de contexto multi-tenant
  com `set_workspace`/`reset_workspace`/`workspace_scope` via
  `contextvars`. Validacao: `^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$` (sem
  trailing `-`/`_`). `__all__` e `default` sao reservados. Helper
  `default_workspace_from_env()` le `HIVE_DEFAULT_WORKSPACE`.

- **K10 — Middleware FastAPI** (`sinapse-api.py`): le header
  `X-Workspace-Id` por request e injeta no contextvar via
  `set_workspace()`. Sem header, usa `HIVE_DEFAULT_WORKSPACE` (default
  'default'). Token e restaurado em `finally`, sem vazar workspace
  entre requests.

- **K10 — Endpoint `GET /api/v1/workspaces`**: lista workspaces ativos
  com contagem de neurons/observations por tenant. Aberto (sem
  auth) - retorna apenas contagens, sem conteudo.

- **K10 — Injeção automatica de `workspace_id` em `execute_insert`**
  (`core/database.py`): quando o caller nao passa `workspace_id`,
  o helper pega do `contextvar` (default 'default'). Defensivo:
  checa `PRAGMA table_info` antes de injetar, tabelas legadas/testes
  sem a coluna nao quebram.

- **OTEL — `scripts/services/otel_collector.py`**: stub OTLP/HTTP
  collector em Python puro (zero deps externas alem de stdlib +
  `opentelemetry-proto`). Aceita `/v1/traces` E
  `/api/public/otel/v1/traces` (path canonico Langfuse). Decodifica
  JSON e protobuf binario. Escreve spans em `logs/otel-spans.log`
  como JSONL. Substitui Langfuse v3 self-hosted (que requer
  Postgres+ClickHouse+Redis e nao cabe em dev). Quando o operador
  quiser Langfuse real, basta apontar `LANGFUSE_HOST` para ele.

- **OTEL — `core/telemetry.py` ajuste**: `BatchSpanProcessor` agora
  com `max_export_batch_size=1` e `schedule_delay_millis=1` para flush
  imediato em dev/test. Fallback para `SimpleSpanProcessor` se a
  lib rejeitar os parametros.

- **OTEL — `hive-otel-collector.service` (systemd)**: servico
  gerenciado em `~/.config/systemd/user/`. Ativado. Escreve logs
  em `~/.local/share/systemd/user/` (padrao journald).

- **Quarentena — cron semanal** (`install.sh`): todo domingo 04:00 UTC
  roda `scripts/health/reprocess_quarantine.py --max-age-days 7 >> logs/quarantine-drain.log 2>&1`.
  Drena automaticamente os 1365 items do `archived=2`.

- **17 testes novos** (32 asserções):
  - `tests/unit/test_workspace_runtime.py` — 10 testes (validacao,
    contextvars, LIFO, env fallback, is_reserved).
  - `tests/unit/test_otel_collector.py` — 7 testes (health, metrics,
    JSON, protobuf, Langfuse path, 404, systemd alive).

### Fixed

- **`execute_insert` quebrava em testes de tabela sem `workspace_id`**:
  agora checa `PRAGMA table_info` antes de injetar, nao falha em
  schemas legados.
- **Langfuse v3 self-hosted nao funciona** (requer ClickHouse+Postgres
  +Redis): removido bloco `langfuse-v3` quebrado, adicionado pointer
  para o `otel_collector.py` como alternativa dev.
- **`test_full_session` em loop no CI** (timeout 60s default, nao
  15s): pre-existente, nao causou por v3.7.9.

### Production impact (medido agora)

- `archived=2`: 1365 → 405 (drenagem manual imediata).
- `observations_linked_pct`: 94.47% → 97.67% (linkadas de volta).
- `discoveries_pending`: 375 → 211.
- Tracing spans agora chegam em `logs/otel-spans.log` (3 spans
  confirmados em 50ms cada).
- K10 multi-tenant: 1 workspace (`default`) ativo. `X-Workspace-Id`
  header disponivel para tenants adicionais.

### Test results

- Unit: **555 passed**, 3 skipped, 0 failed (29.00s)
- E2E: **22 passed** (14.97s)
- Real: **59 passed** (168.90s)
- All 4 suites: **PASSED**

### Migration notes

- Sem migration de schema. `workspace_id` ja era coluna em 9 tabelas
  desde v3.6.0.
- Langfuse v3 self-hosted descontinuado. Use `otel_collector.py`
  (incluido) ou Langfuse Cloud.
- sinapse-api agora exige `core.workspace` (path bootstrap adicionado
  no script). Nenhum efeito em outros servicos.

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
