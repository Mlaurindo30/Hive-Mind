# Observabilidade

> **Hive-Mind v3.10.1** — Saúde de backends, saúde do conhecimento (K8), telemetria do Model Gateway e OTEL tracing.
> Documento normativo de observabilidade. Fontes canônicas: [`arquitetura.md`](arquitetura.md) §5 (read flow, circuit breaker), §28 (K8), §31 (contratos pendentes), [`04-infrastructure.md`](04-infrastructure.md) §2/§3 (env, serviços e portas), [`modelos-ia.md`](modelos-ia.md) (telemetria do gateway) e o código: `core/memory/health.py`, `core/memory/circuit_breaker.py`, `core/memory/context_fusion.py`, `core/model_telemetry.py`, `core/telemetry.py`, `scripts/health/knowledge_health.py`, `scripts/health/health_dashboard.py`, `scripts/health/alert_dispatcher.py`.

---

## 1. Visão geral

A observabilidade do Hive-Mind tem **quatro superfícies independentes** que respondem a perguntas distintas:

| Superfície | Pergunta que responde | Onde vive | Ferramenta de superfície |
|---|---|---|---|
| **Saúde de backends** | "Os 7 órgãos de leitura estão vivos?" | `core/memory/health.py` + `core/memory/circuit_breaker.py` | `sinapse_health()` |
| **Saúde do conhecimento (K8)** | "O cérebro está íntegro e cobrindo o que deveria?" | `scripts/health/knowledge_health.py` | `sinapse_health().knowledge_health`, `GET /api/v1/knowledge/health`, `hive-mind` health |
| **Telemetria do Model Gateway** | "Qual modelo respondeu, a que custo, com fallback?" | `core/model_telemetry.py` | logs `[model_gateway]` em stderr |
| **OTEL tracing** | "Onde o tempo foi gasto dentro de uma chamada?" | `core/telemetry.py` | spans OTLP → Langfuse self-hosted |

Nenhuma superfície carrega **payload** (prompt, conteúdo de neurônio, resposta). A disciplina anti-segredo é transversal e descrita na §6 ("Fronteiras").

---

## 2. Saúde dos backends — `sinapse_health()`

`sinapse_health()` (MCP) / `sinapse-write.py health` / `GET /api/v1/health` retornam um único pacote de status. A implementação canônica é `health_check()` em `core/memory/health.py`, que é **pura** (recebe todos os parâmetros como argumentos, sem estado global).

### 2.1 Estrutura da resposta

```json
{
  "timestamp": "...",
  "backends":          { /* alias de compatibilidade = read_backends */ },
  "read_backends":     { "umc": true, "neural_memory": ..., "sqlite_vec": ...,
                         "claude_mem": ..., "graphify": ..., "graphiti": ..., "filesystem": ... },
  "components":        { "neural_memory": ..., "claude_mem": ..., "sqlite_vec_worker": ...,
                         "graphify_graph": ..., "graphiti": ..., "rtk": ... },
  "vault":             { "path": ..., "exists": true, "graph_nodes": 1234 },
  "plugin":            { "backends_registered": 7 },
  "knowledge_health":  { ... K8 metrics ... },
  "model_gateway":     { "enabled": ..., "models_total": ..., "healthy": ..., "unhealthy": ..., "default_roles": ... },
  "healthy":           true,
  "components_healthy": true
}
```

- `read_backends`/`backends` é o **contrato correto dos 7 órgãos** fundidos por `sinapse_query`.
- `healthy` é o `AND` lógico de todos os 7 read-backends.
- `components_healthy` é o `AND` lógico dos componentes auxiliares (inclui RTK, que **não** é read-backend).
- `knowledge_health` é calculado em **modo rápido** (`quick=True`) dentro do health check: `observation_vectors` não é inspecionado (custo) e `prune_orphans=False` (nada é podado durante um health check).
- `model_gateway` está **sempre presente**, mesmo desabilitado — um gateway desabilitado não faz probe de rede e reporta `enabled: false` explicitamente (nunca omitido).

### 2.2 Os 7 read-backends

| Backend | Órgão do cérebro | O que verifica | Falha típica |
|---|---|---|---|
| `umc` | Córtex (central) | `query_hybrid` importável (SQLite + FTS5 + vec) | import/schema quebrado |
| `neural_memory` | Córtex (associação) | binário `nmem` executável no PATH | binário ausente |
| `sqlite_vec` | Córtex (vetor local) | worker `:37701` responde `/health` | worker fora, `sqlite_vec` não carregado |
| `claude_mem` | Temporal (hipocampo) | worker `:37700` responde `/health` com `status=ok` | worker fora |
| `graphify` | Occipital (estrutural) | `graph.json` legível com `nodes > 0` | grafo vazio/corrompido |
| `graphiti` | Temporal (causalidade) | FalkorDB acessível (via callable injetado) | FalkorDB `:6379` fora |
| `filesystem` | Parietal (senso imediato) | diretório do vault existe | vault ausente |

> **RTK não é read-backend.** Aparece apenas em `components` (otimização de shell). Nunca deve ser ligado em `sinapse_query`, `context_fusion`, `retrieval_router` ou em qualquer lista `read_backends` (ver [`arquitetura.md`](arquitetura.md) §2.6 e §3.2 de [`04-infrastructure.md`](04-infrastructure.md)).

### 2.3 Circuit breaker

Regra implementada em `core/memory/circuit_breaker.py` (stateless — estado passado como dict):

- Um backend com **≥ 3 falhas consecutivas** nos últimos `cooldown` segundos é **pulado** (circuito aberto). `cooldown` default = **30 s**.
- **Só exceções e timeouts contam como falha.** Resultado vazio (`[]`/`null`) **não** conta — busca sem resultado não é doença.
- Sucesso **zera** o contador de falhas (`failures = 0`).

```python
is_backend_healthy(name, backend_state, log_fn) -> bool   # False => circuito aberto
record_backend_result(name, success, backend_state)       # muta o estado in-place
```

Evento de log quando o circuito abre: `log_fn("warn", "circuit_breaker_open", backend=name, failures=failures)`.

### 2.4 Context Fusion — orçamento de tempo e dedup

`core/memory/context_fusion.py:query_vault_knowledge()` orquestra os backends saudáveis em paralelo:

- **`ThreadPoolExecutor`** com um worker por backend saudável.
- **Global timeout** (`global_query_timeout`, default **8 s**): o que não terminar é cancelado e registrado como `query_timeout` (falha → alimenta o circuit breaker).
- Backends que estouraram o timeout recebem latência sintética `= global_query_timeout`.
- **Dedup cross-backend** na fusão (`_fuse_contexts`): observações deduplicadas por `source_file | title | content[:40]`; nodes por `id | label`.
- Resultado final truncado por `max_observations` e `max_nodes` (ver limites em [`arquitetura.md`](arquitetura.md) §5: `MAX_CONTEXT_CHARS=3000`, `MAX_NODES=5`).

Eventos de log por backend: `backend_latency`, `backend_hit`, `backend_error`, `query_timeout`, `thread_unhandled_error`.

---

## 3. Saúde do conhecimento — `knowledge_health` (K8)

`scripts/health/knowledge_health.py` (v3.6.0) **adiciona** métricas de cobertura de conhecimento. **Não substitui** `health_dashboard.py`, `alert_dispatcher.py` nem `review_writer.py` (esses continuam sendo a saúde da Ínsula). Acesso:

- `sinapse_health()` → bloco `knowledge_health` (modo rápido, read-only).
- `GET /api/v1/knowledge/health` → gate completo (permite `prune=true`).
- CLI: `python scripts/health/knowledge_health.py --json [--fail-closed] [--no-prune] [--no-report]`.
- Relatório Markdown auto-gerado em `cerebro/cortex/insula/saude/knowledge-health-<data>.md` (tipo `knowledge-health`, `auto:gerado — não editar à mão`).

### 3.1 Métricas principais

| Métrica | Sinal | Detalhe |
|---|---|---|
| `neurons_total` | tamanho da memória consolidada | `COUNT(*) FROM neurons` |
| `neurons_vectorized_pct` | cobertura vetorial da memória | `search_vec` / `neurons` |
| `observations_total` | volume temporal indexado | observações não-quarentenadas |
| `observations_linked_pct` | **promoção efetiva** | obs com `neuron_id` preenchido / obs não-quarentenadas |
| `discoveries_pending` | **risco de perda de aprendizado** | `knowledge_candidates.status='candidate'` + observações `type IN (discovery, learning, decision)` com `archived=0` |
| `governance_review_queue` | fila de governança | `{held_total, held_high_risk, held_hypothesis}` — candidatos `status='held'` agrupados por `risk` |
| `summary_vectors_total` | cobertura das cadências | vetores de `summary_vectors` |
| `orphan_vectors` | **índice sujo** | vetores cujo parent não existe (detalhe em `orphan_vector_details`) |
| `orphan_vectors_before_prune` / `orphan_vectors_pruned` | efeito da poda | — |
| `milvus_sync_lag` | **divergência local × produção** | `{available, reason, total_lag, by_collection}` |
| `query_route_distribution` | quais camadas respondem | por `first_route|intent` nos últimos 7 dias |
| `tombstones_total` | esquecimento auditável acumulado | `COUNT(*) FROM knowledge_tombstones` |
| `<collection>_vectorized_pct` | cobertura **por coleção canônica** | 7 coleções (§3.4) |
| `collections` | bloco por coleção | `{source_total, vector_total, vectorized_pct}` |
| `promotion_lag` / `promotion_cost` | backlog e custo LLM por workspace | §30.5 de [`arquitetura.md`](arquitetura.md) |
| `vectors_model_mismatch` | divergência de modelo de embedding dentro de uma coleção | §30.4 de [`arquitetura.md`](arquitetura.md) |

> K8 mede explicitamente as **sete coleções canônicas** — o gate não pode inspecionar apenas `neurons_vectorized_pct`.

### 3.2 Gates fail-closed (SLO)

`evaluate_fail_closed(metrics)` retorna a **lista de falhas** (vazia = saudável). `status` final é `ok` ou `degraded`.

| SLO | Condição de falha |
|---|---|
| Índice limpo | `orphan_vectors > 0` |
| Cobertura de memória | `neurons_total > 0` e `neurons_vectorized_pct` desconhecido |
| Cobertura de documentos | `document_vectors.source_total > 0` e `vectorized_pct` desconhecido |
| **SLO 1 — promoção** | `observations_total >= 100` e `observations_linked_pct < 80%` |
| **SLO 2 — dreno** | `discoveries_pending > 500` |

CLI com `--fail-closed` sai com exit code 1 quando há falhas.

### 3.3 `milvus_sync_lag`

`_milvus_sync_lag()` compara o total local por coleção com `backend.count(collection)` do Milvus.

- Milvus desabilitado (`VECTOR_BACKEND != milvus` e `HIVE_KNOWLEDGE_HEALTH_MILVUS != 1`): `{available: false, reason: "milvus_not_enabled", total_lag: null}` — **comportamento esperado, não falha**.
- Habilitado mas unhealthy: `{available: false, reason: <erro>, total_lag: null}`.
- Habilitado e saudável: `{available: true, total_lag: N, by_collection: {...}}`, onde `lag = max(0, local - remote)`.

Para medir `milvus_sync_lag` real em vez de `milvus_not_enabled`, defina `HIVE_KNOWLEDGE_HEALTH_MILVUS=1` (ou `VECTOR_BACKEND=milvus`).

### 3.4 Coleções canônicas medidas

| Coleção | Fonte (`source_total`) | Tabela de vetores |
|---|---|---|
| `memory_vectors` | `neurons` | `search_vec` |
| `observation_vectors` | observações claude-mem (não medido em `quick`) | `vec_observations` (claude-mem) |
| `document_vectors` | `document_chunks` ∪ `neurons.type='document'` | `vec_documents` |
| `code_vectors` | `neurons.type='code'` | `vec_code` |
| `visual_vectors` | `visual_memories` | `vec_visual` |
| `graph_vectors` | `causal_edges` | `vec_graph` |
| `summary_vectors` | arquivos `.md` de cadência (sessão→anual) | `vec_summary` |

> **Estado de implementação (2026-07-03, `POST_AUDIT_FIX_LOG.md` Q2/R3):** o contrato e o schema existem para as 7 coleções, mas apenas `memory_vectors`, `observation_vectors`, `document_vectors` e `visual_vectors` têm indexação semântica wired end-to-end. `code_vectors`, `graph_vectors` e `summary_vectors` têm tabela + `vector_jobs` enqueue (`core/indexing/vector_jobs_worker.py`), mas **nenhum produtor popula embeddings reais ainda** — trate essas 3 como contrato-alvo, não feature entregue.

### 3.5 Vetores órfãos e esquecimento auditável

- `find_orphan_vectors()` localiza vetores cujo parent não existe (por coleção, via `VECTOR_PARENT_SQL`).
- `prune_orphan_vectors()` chama `forget_vector()` com `reason="orphan_vector"`: **remove** o vetor, limpa `vector_metadata` quando aplicável e **escreve `knowledge_tombstones`** (`target_type`, `target_id`, `collection`, `reason`, `actor`, `workspace_id`, `metadata_json`). Nunca há delete silencioso.
- Razões de `forget` válidas: `secret_leak | expired | superseded | user_request | orphan_vector` (ver [`arquitetura.md`](arquitetura.md) §31.2).

---

## 4. Telemetria do Model Gateway

O Model Gateway (`core/model_gateway.py` + `core/model_registry.py`) é o **único** caminho de execução de LLM. Toda chamada emite registros estruturados via `core/model_telemetry.py`, **sem payload** e com campos redigidos.

### 4.1 `record_call` — métricas por chamada

Campos canônicos (assinatura sem parâmetro de prompt/conteúdo/resposta por design):

| Campo | Tipo | Significado |
|---|---|---|
| `request_id` | string (uuid4) | correlação da chamada |
| `workspace_id` | string | fronteira de isolamento (default `default`) |
| `role` | string \| null | papel que disparou (`dreamer`, `validator`, `synthesis`, ...) |
| `selected_model_id` | string | modelo efetivamente selecionado |
| `provider` | string | provider resolvido |
| `endpoint` | string \| null | **redigido** via `redact_for_export` |
| `capabilities_required` | dict | capabilities exigidas (structured, vision, ...) |
| `fallback_used` | bool | se a cadeia usou fallback |
| `latency_ms` | float | latência arredondada em 2 casas |
| `input_tokens` / `output_tokens` | int \| null | consumo de tokens |
| `cost_estimate` | float \| null | custo estimado |
| `error_type` | string \| null | **redigido** via `redact_for_export` |

Saída: `print(f"[model_gateway] {record}", file=sys.stderr)`.

### 4.2 Hooks canônicos (especificação R10)

| Hook | Evento | Campos-chave |
|---|---|---|
| `record_gateway_attempt` | `gateway_attempt` | `request_id`, `role`, `provider`, `model`, `level`, `gateway_attempted=true` |
| `record_gateway_failure` | `gateway_failure` | `request_id`, `error_class`, `reason` (redigido), `gateway_failed=true` |
| `record_legacy_fallback_used` | `legacy_fallback` | `request_id`, `reason` (redigido), `legacy_fallback_used=true` |
| `record_setup_brain_role_configured` | `setup_brain_role_configured` | `role`, `primary`/`fallback`/`fallback2` (provider+model) |
| `record_provider_skipped_due_to_capability` | `provider_skipped_due_to_capability` | `missing_capability` (redigido) |
| `record_provider_unsupported_skipped` | `provider_unsupported_skipped` | `unsupported_reason` (redigido) |

`record_gateway_attempt` retorna o `request_id` que **deve ser reutilizado** em `record_gateway_failure` / `record_legacy_fallback_used` para correlação.

### 4.3 Classificação de erro (`error_class`)

`record_gateway_failure` exige `error_class` em um destes valores: `auth`, `transient`, `validation`, `rate_limit`, `unknown`.

Política de retry/fallback (ver [`modelos-ia.md`](modelos-ia.md) § "Configuring fallback"):

- **`validation`** → **não** dispara fallback (é qualidade de saída, não disponibilidade); retry no mesmo modelo até `max_retries`, depois `LLMValidationError`.
- **`auth` / 401 / 403 / 402 (saldo)** → pula retries e vai direto para o próximo par.
- **`rate_limit` / 429 / 5xx / timeout** → backoff exponencial (teto 8 s), depois fallback.

### 4.4 Disciplina anti-segredo (R10)

- `record_call` **só aceita campos de metadados** — não existe parâmetro de prompt/conteúdo/resposta.
- Todos os hooks seguem a mesma disciplina: **sem payload**; `endpoint`/`error_type`/`reason`/`missing_capability`/`unsupported_reason` passam por `core.redactor.redact_for_export` antes de qualquer escrita.
- Chaves de API são resolvidas em tempo de chamada via `ModelProfile.api_key_env` (`profile.api_key()`); **nunca** armazenadas no objeto de perfil, **nunca** logadas.

---

## 5. OTEL tracing (Langfuse self-hosted)

`core/telemetry.py` expõe tracing OpenTelemetry → **Langfuse self-hosted** (ver [`09-integration-study.md`](09-integration-study.md) §5 para o rationale original).

- **Ativação:** define `LANGFUSE_PUBLIC_KEY` e `LANGFUSE_SECRET_KEY` (opcional `LANGFUSE_HOST`, default `http://localhost:3100`, opcional `HIVE_SERVICE_NAME`, default `hive-mind`). Sem chaves, `init_telemetry()` retorna `False` e o tracing vira no-op.
- **Resource:** `service.name` e `service.version` (fixado em `3.10.1`).
- **Exportador:** `OTLPSpanExporter` para `<LANGFUSE_HOST>/api/public/otel/v1/traces`, auth `Basic base64(pk:sk)`.
- **Processor:** `BatchSpanProcessor` com `max_export_batch_size=1` / `schedule_delay_millis=1` (dev/test); fallback `SimpleSpanProcessor` se a lib rejeitar parâmetros. Em produção aumentar o batch para reduzir overhead (comentário v3.7.9+ no próprio arquivo).
- **API:**
  - `init_telemetry() -> bool` — idempotente.
  - `span(name, attributes=None)` — context manager; `yield None` quando desabilitado; coerces tipos não-OTel para `str`, preserva `bool/int/float/str` para consultas tipadas.
  - `flush_telemetry()` — `force_flush(timeout_millis=5000)`; warn-once em stderr se o flush falhar.
- **Aviso de segurança:** `LANGFUSE_HOST` em HTTP (não HTTPS) e host **não-local** dispara warn em stderr — Basic auth + traces em cleartext.

---

## 6. Dashboard de saúde da Ínsula (health_dashboard + alert_dispatcher)

Complemento operacional à saúde K8:

- `scripts/health/health_dashboard.py` agrega métricas **M1–M13** num snapshot Markdown em `cerebro/cortex/insula/saude/` (seção `## Alertas` com linhas `- ⚠️`). Consome `knowledge_health`, estado das tasks, `logs/jobs/*-latest.json`, `services.managed.json`, doctor de captura.
- `scripts/health/alert_dispatcher.py` lê o snapshot do dia, extrai os alertas ativos e escreve **uma nota por alerta** em `cerebro/cortex/parietal/inbox/YYYY/MM/DD/alerta-<HHMMSS>-<hash8>.md` (frontmatter `type: health-alert`, `severity: warning`, `metric`, `suggested_action`). Sem LLM, **idempotente por content-hash**. Uso: `--apply` para escrever (default dry-run). Métrica **M13** conta alertas despachados hoje.
- Regras de alerta (severidade) estão no runbook — ver [`incidentes.md`](incidentes.md).

---

## 7. Fronteiras (o que a observabilidade NÃO faz)

1. **Nunca registra payload.** Prompt, conteúdo de neurônio e resposta não têm caminho para a telemetria — `record_call` e os hooks do gateway não têm parâmetro de payload; o texto de query **nunca** entra em telemetria (`query_route_distribution` armazena **hash** da query, não o texto — [`arquitetura.md`](arquitetura.md) §26/§28).
2. **RTK não é read-backend.** Aparece só em `components` e nunca participa de `sinapse_query`/Context Fusion.
3. **Health check não muta.** `sinapse_health` usa `quick=True` e `prune_orphans=False`; poda de órfãos só acontece por ação explícita (`knowledge_health.py` sem `--no-prune`, ou `GET /api/v1/knowledge/health?prune=true`).
4. **Gateway desabilitado não faz probe.** `enabled: false` é reportado explicitamente, sem adicionar latência de rede.
5. **Falha de observabilidade não derruba o fluxo.** OTEL é best-effort; `span()` é no-op sem chaves; `knowledge_health` indisponível vira `{status: "unavailable", error}` em vez de quebrar `sinapse_health`.
6. **Resultado vazio ≠ falha.** Circuit breaker conta apenas exceções/timeouts, nunca resultados vazios.

---

## Referências cruzadas

- [`arquitetura.md`](arquitetura.md) — princípios, read flow, circuit breaker, Model Gateway (ADR-019).
- [`operacao.md`](operacao.md) — comandos de operação, cron, `hive-mind doctor`.
- [`pipeline-dados.md`](pipeline-dados.md) — fluxo Capture→Promotion→Index e as 7 coleções.
- [`instalacao.md`](instalacao.md) — variáveis de ambiente (`LANGFUSE_*`, `VECTOR_BACKEND`, `HIVE_KNOWLEDGE_HEALTH_MILVUS`).
- [`incidentes.md`](incidentes.md) — severidade e runbooks por sintoma.
- [`seguranca.md`](seguranca.md) — disciplina anti-segredo e redação de PII.
- [`modelos-ia.md`](modelos-ia.md) — operação completa do Model Gateway.
- [`blueprint.md`](blueprint.md) — diagramas ASCII de arquitetura.
