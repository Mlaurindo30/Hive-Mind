# Blueprint — Hive-Mind

> Documento de desenho em uma página: o que é o Hive-Mind, o que ele faz, o
> fluxo canônico e as decisões de arquitetura (ADR-level) com as consequências.
>
> **Versão refletida:** v3.10.1 · **Referência normativa:** [`arquitetura.md`](arquitetura.md)
> (canônico; ADRs em §32) · **Fluxogramas:** [`blueprint.md`](blueprint.md) ·
> **Anatomia detalhada:** [`arquitetura.md`](arquitetura.md)

---

## 1. O que é o Hive-Mind

O Hive-Mind é uma **camada de memória universal, persistente e local-first para enxames de agentes de IA**.
Ele resolve a amnésia entre sessões: tudo o que os agentes **fazem** (logs), **veem** (capturas de tela),
**leem** (PDF/DOCX) e **decidem** é consolidado em um único cérebro persistente — o **Unified Memory Core (UMC)** —
e materializado em linguagem natural dentro de um vault Obsidian (`cerebro/`), a fonte única de verdade
legível por humanos e por agentes.

Múltiplos agentes (Claude Code, Codex CLI, Cursor, Gemini CLI, Hermes, OpenClaw, entre outros) compartilham
esse mesmo cérebro via **MCP**, plugin nativo, CLI ou **REST API** — numa única máquina ou entre várias,
sincronizadas por P2P.

Em uma frase: **o Hive-Mind não é apenas RAG local — é um cérebro persistente** com captura temporal,
memória consolidada, documentos, código, visão, grafo estrutural, causalidade temporal e busca
híbrida/vetorial (ver [`arquitetura.md` §22](arquitetura.md)).

### O problema que resolve

| Sem o Hive-Mind | Com o Hive-Mind |
|---|---|
| Cada sessão de agente começa do zero (amnésia entre sessões) | Memória consolidada e recuperável entre sessões e entre agentes |
| Conhecimento espalhado em silos (logs, JSON, Chroma, SQLite) | Um único `hive_mind.db` com múltiplas dimensões (grafo + vetores + FTS + logs) |
| Fatos sem fonte nem auditabilidade | Todo neurônio carrega SHA-256, `source_uri`, evidência e citação |
| Dado perdido em falha de pipeline | Quarentena (`archived=2`) — nada é descartado por falha de promoção |
| Cada agente precisa de plugin próprio | Um único servidor MCP (`sinapse-mcp.py`) serve todos os agentes |

---

## 2. O que o Hive-Mind faz

| Capacidade | Como entrega | Detalhe normativo |
|---|---|---|
| **Captura** | hooks · MCP · CLI · browser · docs · código · capturas de tela · runtime | [`arquitetura.md` §23](arquitetura.md) etapa [1] |
| **Memória temporal** | claude-mem (hipocampo): `user_prompts`, `observations`, `discoveries`, `session_summaries` | §2.6, §7 estágio 0.5 |
| **Consolidação** | Dream Cycle (Hive-Dreamer) — a cada 4h (`0 */4 * * *` / `PT4H`) | §7, `runtime.yaml` |
| **Promoção** | Knowledge Intake (K3) → Promotion Layer (K4): Distiller → Validator → Router | §27 |
| **Memória anatômica** | `cerebro/` (vault Obsidian) + UMC — cérebro em 4 lóbulos irmãos | §2, §12 |
| **Indexação** | FTS5 + `sqlite-vec` (1024d) + Graphify + Graphiti + LightRAG + Milvus (produção) | §24 |
| **Recuperação** | `sinapse_query` (Context Fusion, 7 órgãos) + `RetrievalRouter` (K7, por intenção) | §5, §26 |
| **Resposta com citação** | `citations[{source_uri, offset_start, offset_end, score, parent}]` | §25.2 |
| **Visão** | captura de tela → `visual_memories` (descrição + OCR + neuron_id) | §9 |
| **Documentos** | `DocumentPipeline` (K6): parent/chunk/vector + citação auditável | §25 |
| **Multi-máquina** | Syncthing P2P + UUID v4 + SHA-256 + Síntese Dialética | §8 |
| **Federação** | visibilidade (private/shared/public) + Ed25519 + redação de PII | §19, §30.3 |
| **Acesso** | MCP (16 tools) · plugin Hermes · CLI · REST FastAPI :37702 | §10 |

---

## 3. A regra fundadora

Todo o desenho obedece a uma única regra, registrada em
[`arquitetura.md` §22.2](arquitetura.md):

```text
local-first por operação
born-large por arquitetura
plugável por contrato
anatômico por fonte de verdade
auditável por evidência
```

Nenhum backend externo pode **substituir** o cérebro. Backends externos **aceleram, escalam ou
especializam índices**. A verdade permanece no vault anatômico (`cerebro/`) e no UMC.

### Princípios de desenho (normativos)

1. **Fonte única de verdade legível por humanos** — o vault Obsidian é a camada canônica; SQLite é o índice; Markdown é a verdade. Em divergência, o auditor reconcilia a favor do vault.
2. **Local-first** — funciona 100% offline numa máquina. Cloud e P2P são opcionais e aditivos.
3. **Um banco, múltiplas dimensões** — em vez de graph JSON + claude-mem SQLite + Chroma, o UMC centraliza tudo num único `hive_mind.db`; consultas entre dimensões viram SQL simples.
4. **Agnosticismo de agente e de LLM** — qualquer agente conecta via MCP/CLI/REST; qualquer LLM serve o Dream Cycle via `HIVE_DREAMER_PROVIDER/MODEL`. Nenhum modelo é hardcoded.
5. **Fail-safe, não fail-silent** — pipeline falho manda para quarentena (`archived=2`), nunca descarta; API sem chave não inicia; backend com 3+ falhas entra em circuit breaker (cooldown 30s).
6. **Sem sufixos de versão** em arquivos, código ou schema — sem `v2`, `v3` em nomes; migrações viram `setup_<feature>.py` ou `migrate_<feature>.py` (exceção: nomes upstream).

---

## 4. Fluxo canônico em uma página (9 etapas)

O fluxo de conhecimento do Hive-Mind — da captura à resposta com citação e ao feedback — é um
pipeline de **9 etapas** (K0–K10). Reproduzido de [`arquitetura.md` §23](arquitetura.md)
e [`blueprint.md` §13](blueprint.md):

```text
  Agent / Human / System
          |
          v
  [1] Capture Layer
      hooks · MCP · CLI · browser · documents · code · screenshots · runtime
          |
          v
  [2] Temporal Hippocampus (claude-mem)
      user_prompts · observations · discoveries · session_summaries
      facts / narrative / concepts · files_read / files_modified
          |
          v
  [3] Knowledge Intake (core/knowledge/intake.py — K3)
      normalize · classify · deduplicate · preserve evidence
          |
          v
  [4] Promotion Layer (core/knowledge/promotion.py — K4)
      Distiller → Validator → Router
      raw -> summary -> fact / learning / decision / preference / task / rationale
          |
          v
  [5] Anatomical Memory
      cerebro/ + UMC:
        cortex temporal · frontal · parietal · occipital · insula
        cerebelo · diencefalo · tronco
          |
          v
  [6] Index Layer
      FTS · sqlite-vec · Milvus · vec_observations · Graphify · Graphiti · LightRAG
      (7 canonical collections — K1)
          |
          v
  [7] Retrieval Router (core/retrieval/router.py — K7)
      classify intent → choose temporal · memory · document · code · graph · chunk · hybrid
          |
          v
  [8] Answer + Citation
      answer with source · evidence · path · date
      (citations[{source_uri, offset_start, offset_end, score, parent}])
          |
          v
  [9] Feedback
      new observation, decision, learning, or task
```

**Regra de borda (normativa):**

1. Cada etapa é fracamente acoplada: falha na [4] **não bloqueia** [1]–[3] (a observação retorna como `archived=0` ou `archived=2`).
2. Cada escritor declara contrato explícito de escrita (§27.4): cria observação? arquivo anatômico? neurônio? vetor? aresta? tarefa/meta? evidência? chave de idempotência?
3. **Nada é apagado por falha de promoção**: erro transitório → `archived=0` (retry); erro estrutural → `archived=2` (quarentena com razão).

---

## 5. Decisões de desenho (ADR-level)

Cada decisão abaixo é um **ADR registrado** — contexto, escolha, racional e, sobretudo, **consequência aceita**.
O registro canônico completo (ADR-001 a ADR-019) vive em
[`arquitetura.md` §32](arquitetura.md); se qualquer outro documento
discordar de um ADR ali, **§32 prevalece**.

### 5.1 Por que o vault Obsidian é a fonte de verdade (ADR-001)

**Decisão:** o vault Obsidian com frontmatter YAML + WikiLinks é o armazenamento primário; o SQLite é apenas o índice.

**Racional:** Markdown em texto puro é git-friendly, agnóstico de ferramenta e legível sem software especial. O Obsidian
é um editor maduro com graph view, backlinks e ecossistema de plugins. Em divergência, **o auditor reconcilia a favor do vault**.

**Consequências aceitas:**
- Dependência do Watcher para manter o SQLite sincronizado em tempo real (~2s).
- O Obsidian é opcional — o vault funciona sem ele.
- Disciplina de "convenção crítica" (K3/K4): arquivos grandes podem existir para leitura humana, mas a **unidade pesquisável é atômica** (`Patterns.md` é referência humana; cada aprendizado vira `type=learning` individual em `cortex/temporal/`).

### 5.2 Born-large por arquitetura (ADR-010/011/012/013/014/015)

**Decisão:** separar **captura, promoção, armazenamento, indexação e recuperação desde o dia um** — sem depender de
refatoração estrutural tardia para suportar Milvus, pipelines de documento avançados ou roteadores compostos. O Hive-Mind
**nasce pronto para escalar** ("born ready to scale"):

- **K3/K4 — promoção em camadas** (ADR-010): `Knowledge Intake` (normalizar/classificar/dedup) separado de `Promotion Layer` (Distiller → Validator → Router → Persistência → Indexação). Torna a promoção **idempotente** e **testável sem LLM real**, com modo `candidate-only`.
- **K1 — 7 coleções vetoriais canônicas** (ADR-011): `memory_vectors`, `observation_vectors`, `document_vectors`, `code_vectors`, `visual_vectors`, `graph_vectors`, `summary_vectors` — cada uma com metadados canônicos. Uma coleção "tudo" poluiria o ranking e impediria cobertura por tipo.
- **K0 — contrato único de vetor** (ADR-012): `upsert/delete/query/hybrid_query/count/health`, independente do backend (sqlite-vec ↔ Milvus). A aplicação **nunca chama Milvus fora do contrato**.
- **K6 — documentos com parent/chunk/citação** (ADR-013): todo documento vira `document_memories` (parent) + `document_chunks` (átomos) + `document_vectors` (vetores). Sem parent, chunk é texto solto — não auditável, não deduplicável, não re-ingestável.
- **K7 — roteamento por intenção** (ADR-014): `RetrievalRouter` classifica a intenção **antes** de buscar e devolve `retrieval_path` + `citations` + `confidence` + `missing_context`.
- **K10 — workspace como fronteira de isolamento** (ADR-015): toda tabela crítica carrega `workspace_id` (default `'default'`); Milvus usa `partition_key=workspace_id`. Vazamento entre workspaces é **bug de segurança**, não questão de ranking.

**Consequências aceitas:**
- Mais tabelas UMC e mais metadados por vetor (mitigado por `vector_metadata` e pela identidade de coleção `(name, embedding_model, dim)`).
- O contrato de vetor precisa permanecer estável; mudança de schema Milvus exige migração de embedding versionada (§30.4).
- Classificadores de intenção podem falhar (mitigado por fallback para `sinapse_query`/Context Fusion e métrica `intent_accuracy`).
- Toda consulta carrega `workspace_id` (mitigado por índices quentes `(workspace_id, …)` e default `'default'`).

### 5.3 Quarentena em vez de descarte (ADR-008 + ADR-016)

**Decisão:** pipeline falho grava `archived=2` em vez de apagar ou ignorar a observação. ADR-016 refina o contrato:
**erro transitório** (rede fora, crédito zero, schema novo) → `archived=0` (retry futuro); **erro estrutural** → `archived=2`
(quarentena com razão).

**Racional:** dado de memória é valioso; falhas transitórias não devem causar perda permanente de contexto. O contrato
normativo é **fail-safe, não fail-silent**.

**Consequências aceitas:**
- Acúmulo de dados em quarentena exige limpeza periódica — mitigado por `K8 knowledge_health` expondo
  `observations_pending`/`discoveries_pending` como gate, pelo pipeline de reprocessamento, e por
  `forget()` com razão (`secret_leak | expired | superseded | user_request | orphan_vector`, §31.2).
- O `hipocampo/` do lóbulo temporal é a área de staging do Dream Cycle + quarentena (§2.1.1).

### 5.4 Promoção proporcional ao risco

**Decisão:** a promoção de observação bruta → conhecimento tipado não é uniforme. Ela é **proporcional ao risco**:
o que está verificado e é de baixo risco é promovido já; hipóteses só sobem depois de drenadas/validadas; o que é
de alto risco (potencialmente errado ou perigoso) só sobe com aprovação explícita.

**Mecanismos que implementam isso:**

| Mecanismo | O que garante | Fonte |
|---|---|---|
| **Disciplina epistêmica (verified vs hypothesis)** | `sinapse_save_decision`/`sinapse_save_learning` com `evidence` grava `confidence: verified`; sem evidência grava `hypothesis`, rebaixada no ranking até validação | protocolo MCP |
| **Review TTL (staleness)** | cada decisão/aprendizado carrega `next_review` (default 90d); vencido, o `RetrievalRouter` aplica penalidade `HIVE_STALENESS_PENALTY` (default 0.85) — nunca exclui, só rebaixa | protocolo MCP |
| **Validador no Promotion Layer** | o Validator (Pydantic) aprova ou rejeita; rejeitado volta ao Distiller (max 2 retries); estruturalmente inválido vai para quarentena | §7 estágio 2 |
| **Regra de promoção automática** | permitido: `decision`, `learning`, `project_status`, `operational_fact`, `goal/task`, `rationale` (com fonte rastreável); proibido: transformar cada bullet em fato, criar neurônio sem fonte, vetorizar duplicatas sem `parent_id`, promover opinião temporária a decisão de arquitetura, sobrescrever decisões sem conflito/`invalid_at` | §27.3 |

**Consequências aceitas:**
- Notas não-verificadas permanecem rebaixadas até validação; hipótese refutada deve ser **corrigida**, não deixada no lugar (uma hipótese refutada no lugar envenena a recuperação futura).
- O custo de promoção é um LLM (classificar) + um embedding por observação — escala como fila com backpressure e teto de custo por workspace (§30.5, `HIVE_PROMOTION_BUDGET_*`).

### 5.5 MCP como protocolo universal de integração (ADR-003)

**Decisão:** expor as ferramentas via **MCP stdio** (`sinapse-mcp.py`, 16 tools) em vez de construir plugins específicos por agente.

**Racional:** MCP é um padrão aberto adotado por Anthropic, OpenAI, GitHub e a comunidade. Um único servidor serve
todos os agentes sem adaptação.

**Consequências aceitas:**
- Menos integração automática (hooks) do que plugins nativos — compensado por CLI (`sinapse-write.py`) e hooks externos (SessionStart, PostToolUse, Stop via `sinapse-hook.py`).
- O Hermes mantém o **plugin nativo** (`plugins/hermes/sinapse-memory.py`, hooks `pre_gateway_dispatch` / `post_tool_call` / `on_session_end`) — o único componente ciente de todas as camadas.
- Único bloco de instruções operacionais: `config/sinapse-agent-prompt.md`, injetado entre marcadores `<!-- BEGIN HIVE-MIND SINAPSE -->` / `<!-- END HIVE-MIND SINAPSE -->` — corrigir esse prompt é a única ação necessária para propagar política operacional a todas as instalações limpas futuras.

### 5.6 Model Gateway como camada canônica de execução de LLM (ADR-019)

**Decisão:** `core/model_gateway.py` + `core/model_registry.py` são o **único** caminho de execução de LLM.
`core/llm_client.call_llm_with_fallback` é um wrapper fino que delega ao `ModelGateway.from_combined_config()`;
o legado `_legacy_call_llm_with_fallback` só é alcançável via `HIVE_FORCE_LEGACY_LLM=true` (bypass de emergência)
ou `image_path` (ponte de visão). `MODEL_GATEWAY_MODE=auto` (default) usa o gateway e cai no legado em falha com
warning + telemetria; `on` torna o gateway obrigatório; `MODEL_GATEWAY_ENABLED` é shim deprecado.

**Racional:** uma única fonte de verdade para execução de LLM elimina a confusão de caminho duplo (gateway opt-in ao lado
do código legado). Novos backends de inferência entram via overrides `config/model-gateway.yaml`, não por tocar call sites.

**Consequências aceitas:**
- O registro unifica três fontes de config (legado `HIVE_{ROLE}_*` + `PROVIDERS_CONFIG` + YAML), criando pequena
  superfície de migração para operadores que fixavam `roles.<name>.provider` em YAML — mitigado por
  `ModelRegistry.validate()` reportando `unsupported_explicit` e por `setup-brain.py` imprimindo a tabela resolvida.
- Fallback explícito (nunca sucesso silencioso) e telemetria redatada preservam as garantias do caminho legado.

### 5.7 Demais ADRs de fundação (resumo com consequência)

| ADR | Decisão | Consequência aceita |
|---|---|---|
| ADR-002 | Busca híbrida paralela em 7 órgãos (UMC, NeuralMemory, sqlite-vec, claude-mem, Graphify, Graphiti, filesystem) com fusão e dedup | I/O um pouco maior; mitigado por circuit breaker (30s após 3+ falhas) e rerank opcional |
| ADR-004 | Escrita atômica via `tempfile.mkstemp()` + `os.replace()` | Levemente mais complexo; justificado para dado de memória persistente |
| ADR-005 | API de memória em nuvem (FastAPI :37702, Bearer), fail-closed sem `HIVE_MIND_API_KEY` | Exige rede estável; fallback automático para local quando `cloud.enabled=false` |
| ADR-006 | Saída estruturada Pydantic em todo o Dream Cycle (`model_validate_json`) | Uma chamada de validação LLM extra por execução |
| ADR-007 | UUID v4 em todas as PKs | IDs menos legíveis em log; irrelevante para uso programático |
| ADR-009 | Config de LLM por papel com herança do Dreamer e fallback opt-in; **cascata automática de provider rejeitada** | Até 16 variáveis de ambiente; caso mínimo segue em 2 (`HIVE_DREAMER_PROVIDER/MODEL`) |
| ADR-017 | Cadência hierárquica sessão→diário→semanal→mensal→anual com papéis de LLM dedicados | Mais papéis a configurar; mitigado por herança do `dreamer` no `setup-brain` |
| ADR-018 | Contrato negativo de vendoring via `components.lock.json` (só clones com commit fixado) | Manutenção do lock; mitigado por geração via `install.sh` + revisão de PR |

---

## 6. Estado atual (v3.10.1)

| Frente | Estado |
|---|---|
| **Versão** | `3.10.1` (release 2026-08-15) |
| **Windows nativo** | runtime Windows nativo em `.venv` local, sem WSL2; host agents (Claude Code, Cursor, Copilot) alcançam a memória diretamente; supervisor `hive-mind services` |
| **Model Gateway** | camada canônica de execução de LLM (`MODEL_GATEWAY_MODE=auto`); `reasoning=True` por papel (dreamer/validator/synthesis) |
| **Dream Cycle** | a cada 4h (`0 */4 * * *` / `PT4H`), alinhado ao `runtime.yaml` |
| **Docker** | `Dockerfile` + `docker-compose.yml` unificados (FalkorDB, Milvus, RAGFlow stack + app); `docker/entrypoint.sh` materializa o vault idempotentemente; restart policy `unless-stopped` nos serviços obrigatórios |
| **Captura** | captura universal de providers (`src/hive_mind/capture/`): transporte único (`engine.py`), identidade por provider (`identity.py`), idempotência por content-hash, `SeenStore` em SQLite WAL |
| **Fases** | HM-01…HM-12 entregues · K0–K10 implementadas e revalidadas em local-full · gate K9 real em `tests/run_real_knowledge.sh` |

> **Nota sobre status por fase:** o registro de fase vive em [`arquitetura.md` §21](arquitetura.md)
> ("Phase Governance") e §22–§31 (Born-Large). Ver [`operacao.md`](operacao.md) e [`runtime.md`](runtime.md) para o
> control plane (`hive-mindd`, `config/runtime.yaml`).

---

## 7. Leitura complementar (docs novos)

| Tema | Documento |
|---|---|
| Anatomia do cérebro, UMC, caminhos canônicos, órgãos externos | [`arquitetura.md`](arquitetura.md) |
| Capture → Intake → Promotion → Indexação | [`pipeline-dados.md`](pipeline-dados.md) |
| LLMs, embeddings, papéis, fallback | [`modelos-ia.md`](modelos-ia.md) |
| Control plane e daemon (`hive-mindd`) | [`runtime.md`](runtime.md) |
| Interface de linha de comando | [`cli.md`](cli.md) |
| Integração de agentes (MCP/plugin/hooks) | [`agentes.md`](agentes.md) |
| Captura universal de providers | [`captura.md`](captura.md) |
| Instalação (incl. Windows nativo) | [`instalacao.md`](instalacao.md) |
| Operação (cron/jobs/backup) | [`operacao.md`](operacao.md) |
| Observabilidade e métricas de saúde (K8) | [`observabilidade.md`](observabilidade.md) |
| Resposta a incidentes e recuperação | [`incidentes.md`](incidentes.md) |
| Segurança (segredos, redação, assinatura) | [`seguranca.md`](seguranca.md) |
| Como desenvolver e estender | [`desenvolvimento.md`](desenvolvimento.md) |
| Handover de estado | [`HANDOVER.md`](HANDOVER.md) |
