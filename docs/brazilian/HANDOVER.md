# HANDOVER — Transferência para Sustentação

> **Hive-Mind v3.10.1** (release 2026-08-15) — Documento de transferência do projeto para a equipe de sustentação.
> Objetivo: quem assume a manutenção deve conseguir (1) entender o que é, (2) localizar cada área, (3) conhecer as pendências conhecidas e (4) validar que está apto a operar, **sem** depender de quem construiu.

---

## 1. O que é o Hive-Mind

O Hive-Mind é uma **infraestrutura de inteligência coletiva e multimodal**: unifica o que o agente faz, vê e lê numa única memória persistente e distribuída, organizada como uma **arquitetura de conhecimento born-large** (nascida pronta para escalar, local-first por operação, plugável por contrato). A fonte de verdade é o vault anatômico (`cerebro/`, Obsidian/Markdown); o SQLite (`hive_mind.db` com `sqlite-vec` + FTS5) é o índice.

Regra-resumo: **local-first por operação · born-large por arquitetura · plugável por contrato · anatômico por fonte de verdade · auditável por evidência**.

Fluxo canônico (9 passos): `Captura → Hipocampo Temporal (claude-mem) → Knowledge Intake (K3) → Promotion Layer (K4) → Memória Anatômica → Indexação → RetrievalRouter (K7) → Resposta com citação → Feedback`.

### 1.1 Stack em uma linha

| Camada | Tecnologia |
|---|---|
| Cérebro (UMC) | `hive_mind.db` — SQLite + `sqlite-vec` (1024d `snowflake-arctic-embed2`) + FTS5 + grafo + multimodal + `workspace_id` |
| Estrutural | Graphify (clone `integrations/`, pin commit) |
| Temporal | claude-mem (TypeScript/Bun, wrapper, `~/.claude-mem`) |
| Vetores | `VectorBackend` — `sqlite_vec` (local) / Milvus (produção) |
| Documentos | `DocumentPipeline` (K6) + RAGFlow headless (opcional) |
| Retrieval | `RetrievalRouter` (K7) + LlamaIndex (rerank, opcional) |
| Execução LLM | `core/model_gateway.py` (único caminho, ADR-019) |
| Acesso | MCP (16 tools) · plugin Hermes · CLI · REST `:37702` |
| Distribuição | Syncthing (P2P) + UUID v4 + SHA-256 + Síntese Dialética + Ed25519 |

---

## 2. Estado atual

- **Versão:** `3.10.1` (concordância em 5 fontes: `pyproject.toml`, `npm/package.json`, `core/version.py`, `scripts/services/sinapse-api.py`, `scripts/services/sinapse_mcp.py`; validador `scripts/release/validate_package.py` trava o piso SemVer `>=3.10`).
- **Fases:** HM-01 a HM-12 ✅; **K0–K10** implementadas (K7 `v3.5.0`, K8 `v3.6.0`; K9/K10 como contrato). Ver [`arquitetura.md`](arquitetura.md) §21.
- **Model Gateway** é o caminho canônico de execução LLM (`MODEL_GATEWAY_MODE=auto` default; `HIVE_FORCE_LEGACY_LLM=true` como bypass emergencial).
- **Windows-native runtime** maduro na v3.10.1 (Dockerfile + docker-compose, scheduler nativo, supervisor).
- **Testes:** suíte dinâmica (medir com `rg -n "^\s*(async\s+def|def)\s+test_" tests | wc -l`; não confiar em número fixo). Gate real K9 separado (`tests/run_real_knowledge.sh`).

---

## 3. Donos e fronteiras — onde está cada área

Tabela **área → onde está (código) → referência documental**. Nenhuma área é órfã; cada uma tem um dono de escrita e um contrato.

| Área | Onde está | Referência |
|---|---|---|
| Arquitetura canônica (princípios, UMC, fluxos, ADRs 001–019, Born-Large §22–§31) | — (normativo) | [`arquitetura.md`](arquitetura.md) (canônico, prevalece sobre qualquer outro em caso de divergência) |
| Cérebro/UMC (schema, conexões, WAL, migrações) | `core/umc_schema.sql`, `core/database.py` | [`arquitetura.md`](arquitetura.md) §4; [`04-infrastructure.md`](04-infrastructure.md) §6.1 |
| Vault anatômico (constantes de caminho) | `core/paths.py` | [`arquitetura.md`](arquitetura.md) §2.7, §12 |
| Model Gateway (execução LLM) | `core/model_gateway.py`, `core/model_registry.py`, `integrations/model_gateway/` | [`modelos-ia.md`](modelos-ia.md); ADR-019 |
| Auth multi-provedor (roles) | `core/auth.py` (`PROVIDERS_CONFIG`, `get_role_config`) | [`arquitetura.md`](arquitetura.md) §11; [`02-ai-models.md`](02-ai-models.md) |
| Knowledge Intake (K3) | `core/knowledge/intake.py` | [`arquitetura.md`](arquitetura.md) §27.1 |
| Promotion Layer (K4) | `core/knowledge/promotion.py`, `claude_mem_bridge.py` | [`arquitetura.md`](arquitetura.md) §27.3–27.5 |
| DocumentPipeline (K6) | `core/knowledge/document_pipeline.py` | [`arquitetura.md`](arquitetura.md) §25 |
| VectorBackend (K1) | `core/vector_backend.py`, `core/vector_collections.py` | [`arquitetura.md`](arquitetura.md) §24 |
| RetrievalRouter (K7) | `core/retrieval/router.py`, `core/search.py` | [`arquitetura.md`](arquitetura.md) §26 |
| Saúde do conhecimento (K8) | `scripts/health/knowledge_health.py` | [`arquitetura.md`](arquitetura.md) §28; [`observabilidade.md`](observabilidade.md) §3 |
| Saúde da Ínsula (M1–M13) | `scripts/health/health_dashboard.py`, `alert_dispatcher.py` | [`observabilidade.md`](observabilidade.md) §6 |
| Dream Cycle / Cadência (K5) | `scripts/dream/dream_cycle.py`, `{session_consolidator,daily,weekly,monthly,yearly}_*.py`, `pattern_distiller.py` | [`arquitetura.md`](arquitetura.md) §7, §29 |
| Captura | `scripts/capture/visual_capture.py`, `scripts/capture/capture_adapters.py` | [`docs/capture/providers.md`](capture/providers.md) |
| MCP / CLI / REST | `scripts/services/sinapse_mcp.py`, `sinapse-write.py`, `sinapse-api.py` | [`arquitetura.md`](arquitetura.md) §10 |
| Registro de agentes | `src/hive_mind/agents/` (wrappers em `scripts/setup/`) | [`docs/agentes.md`](agentes.md), [`AGENTS.md`](../AGENTS.md) |
| P2P / conflito | `scripts/health/audit_memory.py`, `core/database.register_ambiguity`, `scripts/dream/semantic_diff.py` | [`arquitetura.md`](arquitetura.md) §8; [`07-p2p-sync-setup.md`](07-p2p-sync-setup.md) |
| Federação (HM-12) | `core/signing.py` (Ed25519), `core/redactor.py` (PII), export endpoint | [`arquitetura.md`](arquitetura.md) §19; [`seguranca.md`](seguranca.md) |
| Telemetria / OTEL | `core/model_telemetry.py`, `core/telemetry.py` | [`observabilidade.md`](observabilidade.md) §4–§5 |
| Circuit breaker / Context Fusion | `core/memory/circuit_breaker.py`, `core/memory/context_fusion.py`, `core/memory/health.py` | [`arquitetura.md`](arquitetura.md) §5; [`observabilidade.md`](observabilidade.md) §2 |
| Instalação | `install.sh`, `install.ps1`, `src/hive_mind/install/`, `Dockerfile` + `docker-compose.yml` | [`instalacao.md`](instalacao.md), [`15-windows-clean-install.md`](15-windows-clean-install.md) |
| Runtime / scheduler / supervisor | `config/runtime.yaml`, `src/hive_mind/maintenance/` | [`docs/runtime.md`](runtime.md), [`docs/runtime.md`](runtime.md) |
| Backup / recovery | `scripts/health/backup_databases.py`, `scripts/utils/recover.sh` | [`04-infrastructure.md`](04-infrastructure.md) §5; [`arquitetura.md`](arquitetura.md) §16 |
| Vendorização (contrato negativo) | `components.lock.json` | [`arquitetura.md`](arquitetura.md) §2.6, §22.3; ADR-018 |
| Testes | `tests/{smoke,unit,integration,e2e,real}` | [`arquitetura.md`](arquitetura.md) §15; [`tests/README.md`](../tests/README.md) |
| Identidade canônica | `docs/captura.md` | [`docs/captura.md`](captura.md) |

### 3.1 Fronteiras que a sustentação deve defender

1. **Vault é a verdade.** Em divergência, o auditor reconcilia **a favor do `cerebro/`**.
2. **Órgãos externos não são fonte de verdade.** Milvus, RAGFlow e LlamaIndex aceleram/escalam/especializam índices; nunca substituem o vault + UMC. RAGFlow: nunca fonte; store é cache de ingestão.
3. **`components.lock.json` é contrato negativo.** Clones (`graphify`, `neural-memory`, `rtk`) pinados por commit. Se Milvus, RAGFlow ou LlamaIndex aparecerem lá, a implementação está **errada**.
4. **Nunca chamar backend bruto.** Use apenas `sinapse_*`/`search_memories`; nunca `nmem`, `claude-mem`, `graphify` ou `falkordb` direto.
5. **Nunca hardcodar modelo.** Obedeça estritamente `HIVE_*_PROVIDER/MODEL`.
6. **Sem sufixo de versão em arquivo/classe/tabela.** Use sufixo semântico (`setup_crdt.py`, não `migrate_to_v2.py`).
7. **Quarentena nunca descartada; hipótese refutada corrigida no lugar.** Ver [`incidentes.md`](incidentes.md) §4.
8. **Nunca modificar `cerebro/` sem o Watcher ativo** (ou rodar `./scripts/graph/build-graph.sh` depois).

---

## 4. Pendências conhecidas (assuma com conhecimento de causa)

| # | Pendência | Onde está documentado | Impacto |
|---|---|---|---|
| 1 | **3 coleções vetoriais sem produtor** — `code_vectors`, `graph_vectors`, `summary_vectors` têm tabela + `vector_jobs` enqueue, mas nenhum produtor popula embeddings reais ainda | [`arquitetura.md`](arquitetura.md) §24.2 (nota de status) | `*_vectorized_pct` dessas 3 coleções é contrato-alvo, não métrica real |
| 2 | **Reranker** — `HIVE_RETRIEVAL_RERANKER=1` entrega rerank lexical determinístico fail-open; cross-encoder local é opt-in (`HIVE_RERANKER_PROVIDER/MODEL` + extra `reranker`) | [`arquitetura.md`](arquitetura.md) §31.1 | Reordenação por relevância só parcial |
| 3 | **Esquecimento intencional** — `forget()` cobre `orphan_vector`; `secret_leak`, `expired`, `superseded`, `user_request` ainda são contrato (mesma tabela `knowledge_tombstones`) | [`arquitetura.md`](arquitetura.md) §31.2 | Delete auditável de dados não-órfãos pendente |
| 4 | **Avaliação de retrieval** — golden set `tests/real/golden_retrieval.jsonl` com `precision@k`/`recall@k`/`intent_accuracy` é contrato | [`arquitetura.md`](arquitetura.md) §31.3 | Qualidade de resposta não medida pelo gate K8 (K8 mede cobertura) |
| 5 | **Doc numeração ausente** — `06-gap-analysis.md`, `10-…`, `11-knowledge-promotion-architecture.md`, `12-…`, `13-*.md` são citados mas **não existem neste checkout**; apontam para `arquitetura.md §22–§31` | [`docs/README.md`](README.md) §nota de manutenção | Links quebrados até recriação/remoção intencional |
| 6 | **Documentação STALE/CONTRADICTORY presumida** — `README.md`, `AGENTS.md`, `docs/README.md`, `arquitetura.md` (pré-redesign), `instalacao.md`; auditoria linha-a-linha pendente |  | Divergências doc×código documentadas lá (tabela "Divergências") |
| 7 | **Milvus/RAGFlow opcionais** — sem `VECTOR_BACKEND=milvus`, K8 reporta `milvus_sync_lag.available=false` (esperado). Ambos são wrapper/container, nunca clonados | [`04-infrastructure.md`](04-infrastructure.md) §2.3 | Sem esses, usa `sqlite_vec` local |
| 8 | **Model Gateway — limitações** — LiteLLM só proxy HTTP; streaming não implementado; visão delegada ao caminho legacy; tool-calling declarado mas não exercitado; SSRF básico (sem anti DNS-rebinding) | [`modelos-ia.md`](modelos-ia.md) § "Known limitations" | Restrições operacionais conhecidas |
| 9 | **Arquivos de convenção antiga** no vault (`cerebro/cortex/frontal/trabalho/ativo/`) — 4 arquivos com numeração sem prefixo de projeto; renomear no próximo edit manual (via Syncthing, não git) | [`arquitetura.md`](arquitetura.md) §21 | Cosmético/consistência |
| 10 | **`MODEL_GATEWAY_ENABLED` deprecated** — shim de `MODEL_GATEWAY_MODE`; será removido | [`modelos-ia.md`](modelos-ia.md) § "Operating modes" | Migração de operadores |

---

## 5. Checklist de assumir (validação de aptidão)

Execute, na ordem, e **registre o resultado com evidência**. Só considere a transferência completa quando todos passarem.

1. **Ambiente:** `python --version` (3.10+), `sqlite3 --version` (3.44+), `uv --version`, `syncthing --version`.
2. **Saúde dos backends:** `sinapse_health()` (ou `python scripts/services/sinapse-write.py health`) → os 7 `read_backends` e o bloco `knowledge_health` presentes.
3. **Saúde do conhecimento:** `python scripts/health/knowledge_health.py --json` → `status=ok` e lista `failures` vazia (ou entender cada falha).
4. **Model Gateway:** `python scripts/analytics/model_benchmark.py --health` → perfis habilitados resolvem.
5. **REST API:** subir com `HIVE_MIND_API_KEY` e chamar `GET /api/v1/health`.
6. **Testes mínimos:** `bash tests/smoke/test_smoke.sh` (mínimo aceitável); ideal `./tests/run_all.sh`.
7. **Backup:** confirmar que `backup_databases.py` roda e o último backup tem < 36 h.
8. **Dream Cycle:** confirmar `logs/dream-cycle.log` com última execução < 36 h e `status=ok`.
9. **Watcher:** `pgrep -f start-watcher` (POSIX) ou task/serviço equivalente no Windows ativo.
10. **Recovery:** conhecer `./scripts/utils/recover.sh` (e não tê-lo executado sem necessidade).
11. **Acesso à memória:** `sinapse_query("<tópico>")` retorna contexto; `sinapse_temporal_search` localiza sessões recentes.
12. **Segredos:** confirmar `.env` fora de versionamento (`git status` não lista `.env`/`*.db`/`config/keys/`).

---

## 6. Sequência de leitura recomendada

1. [`../README.md`](../README.md) → visão geral pública.
2. [`arquitetura.md`](arquitetura.md) → referência canônica (leia §1–§13 e depois §22–§32).
3. [`04-infrastructure.md`](04-infrastructure.md) → serviços, portas, env, cron.
4. [`observabilidade.md`](observabilidade.md) → saúde de backends, K8, telemetria, OTEL.
5. [`incidentes.md`](incidentes.md) → severidade e runbooks.
6. [`seguranca.md`](seguranca.md) → segredos, PII, assinatura, validação.
7. [`modelos-ia.md`](modelos-ia.md) → execução LLM e limitações.
8.  → estado da documentação e divergências conhecidas.
9.  e  → histórico de entregas e dívidas.

> Documentos novos do squad (nomes em português): [`arquitetura.md`](arquitetura.md), [`operacao.md`](operacao.md), [`pipeline-dados.md`](pipeline-dados.md), [`instalacao.md`](instalacao.md), [`desenvolvimento.md`](desenvolvimento.md), [`blueprint.md`](blueprint.md). Quando existirem, são as portas de entrada por perfil de leitor; até lá, os arquivos canônicos listados acima são a verdade.

---

## Referências cruzadas

- [`observabilidade.md`](observabilidade.md) — superfícies de saúde e telemetria.
- [`incidentes.md`](incidentes.md) — severidade, runbook, escalação, fronteiras.
- [`seguranca.md`](seguranca.md) — segredos, PII, assinatura, classificação de dados.
- [`arquitetura.md`](arquitetura.md) · [`operacao.md`](operacao.md) · [`pipeline-dados.md`](pipeline-dados.md) · [`instalacao.md`](instalacao.md) · [`desenvolvimento.md`](desenvolvimento.md) · [`blueprint.md`](blueprint.md) — documentos do squad (em construção).
