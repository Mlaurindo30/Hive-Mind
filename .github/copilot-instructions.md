<!-- BEGIN HIVE-MIND SINAPSE (auto-managed by register-mcp.sh â€” do not edit) -->
# Protocolo Hive-Mind (sinapse-memory) â€” OBRIGATÃ“RIO

VocÃª tem as 15 tools `sinapse_*` e `search_memories`. Este Ã© o protocolo de
trabalho; siga sempre, sem exceÃ§Ã£o. Os backends crus (NeuralMemory, claude-mem,
Graphify, Graphiti/FalkorDB, UMC, sqlite-vec, filesystem) sÃ£o federados por
dentro do sinapse via `sinapse_query` (Context Fusion com circuit breaker
e timeout 8s) â€” **nunca os chame diretamente**.

## 0. PrÃ©-checagem (uma vez no inÃ­cio da sessÃ£o)
- `sinapse_health()` â€” confirme que todos os backends estÃ£o operacionais
  antes de trabalhar. Se algum falhar, reporte e use `sinapse_temporal_search`
  ou `search_memories` no modo `text` como fallback.

## 1. Recupere antes de agir (no inÃ­cio de cada tarefa)
| Necessidade | Tool |
|-------------|------|
| Estado/histÃ³rico do projeto, decisÃµes, padrÃµes, cÃ³digo/vault e contexto geral | `sinapse_query("<tema>")` (busca hÃ­brida canÃ´nica: funde UMC + NeuralMemory + sqlite-vec + claude-mem + Graphify + Graphiti + filesystem) |
| Atividade recente de conversas, prompts, sessÃµes e observaÃ§Ãµes brutas do claude-mem | `sinapse_temporal_search("<termos curtos e especÃ­ficos>")` â†’ `sinapse_temporal_timeline(anchor=<id>)` â†’ `sinapse_temporal_get_observations(ids=[...])` |
| SaÃºde/verificaÃ§Ã£o de backends | `sinapse_health()` |

**Regra:** nunca afirme nada sobre o estado/histÃ³rico do projeto sem ter
consultado antes.

**Como pesquisar sem se perder:**
1. Para entender "o que aconteceu no projeto", comece com `sinapse_query`.
   Ele Ã© tolerante a linguagem natural e cruza todos os Ã³rgÃ£os do cÃ©rebro.
2. Se precisar da conversa/prompt/sessÃ£o recente que originou aquilo, use
   `sinapse_temporal_search` como **Ã­ndice textual do claude-mem**. Pesquise
   com termos curtos que provavelmente estÃ£o no texto real. Exemplos bons:
   `"setup-brain modelos"`,
   `"Hive-Mind projeto LLM roles fallback"`, `"Model Configuration Not Persisting"`.
3. Se `sinapse_temporal_search` vier vazio, nÃ£o conclua que nÃ£o existe memÃ³ria:
   reduza a consulta para 2-5 termos exatos, tente o tÃ­tulo retornado por
   `sinapse_query`, ou volte para `sinapse_query` para recuperar contexto
   consolidado.
4. NÃ£o use frases longas, perguntas completas ou muitos filtros misturados em
   `sinapse_temporal_search`; ela Ã© melhor como busca textual/timeline do
   claude-mem, nÃ£o como orquestrador hÃ­brido.
5. Para memÃ³ria temporal bruta, siga o fluxo nativo do `claude-mem`:
   `search â†’ timeline â†’ get_observations`.
   - `sinapse_temporal_search` Ã© o Ã­ndice compacto: encontre IDs/tÃ­tulos.
   - `sinapse_temporal_timeline` mostra contexto cronolÃ³gico ao redor de um ID
     ou de uma query-Ã¢ncora.
   - `sinapse_temporal_get_observations` hidrata o conteÃºdo completo apenas dos
     IDs filtrados. **Nunca** hidrate detalhes antes de filtrar; isso desperdiÃ§a
     tokens e mistura contexto irrelevante.

## 2. Recall sob demanda (durante o trabalho)
| Necessidade | Tool |
|-------------|------|
| NeurÃ´nios/notas por similaridade semÃ¢ntica (HNSW + FTS) | `search_memories(query, top_k, project, mode)` |
| Fatos/decisÃµes com validade temporal (arestas valid_at/invalid_at) | `sinapse_temporal_graph_search("<tema>", num_results)` (deprecated â€” use `sinapse_query`) |
| Busca textual no Ã­ndice do claude-mem global (`~/.claude-mem`) | `sinapse_temporal_search("<termos curtos>")` |
| Contexto cronolÃ³gico ao redor de um resultado temporal | `sinapse_temporal_timeline(anchor=<id>)` ou `sinapse_temporal_timeline(query="<termos>")` |
| Detalhe completo de observaÃ§Ãµes temporais jÃ¡ filtradas | `sinapse_temporal_get_observations(ids=[...])` |
| Busca hÃ­brida geral (todas as camadas; padrÃ£o para contexto do projeto) | `sinapse_query("<tema>")` |
| Consulta vetorial no grafo LightRAG (P4) | `sinapse_rag_query(question, mode?)` |

### Escolha rÃ¡pida das tools

| Pergunta do agente | Use | ObservaÃ§Ã£o prÃ¡tica |
|--------------------|-----|--------------------|
| "Qual Ã© o estado/histÃ³rico do projeto?" | `sinapse_query` | Primeira escolha. Cruza vault, UMC, claude-mem, Graphify, Graphiti, sqlite-vec e filesystem. |
| "Qual prompt/sessÃ£o recente falou disso?" | `sinapse_temporal_search` â†’ `sinapse_temporal_timeline` â†’ `sinapse_temporal_get_observations` | Use termos curtos/exatos, escolha IDs, leia a janela temporal e sÃ³ entÃ£o hidrate detalhes. |
| "Quais neurÃ´nios consolidados existem sobre esse tema?" | `search_memories` | Use `project` quando souber o projeto; `mode="text"` para busca literal. |
| "Preciso de relaÃ§Ãµes multi-hop entre entidades jÃ¡ indexadas." | `sinapse_rag_query` | Depende do LightRAG estar populado; se vier vazio, volte para `sinapse_query`. |
| "Preciso de fatos temporais/causais do Graphiti." | `sinapse_query` | `sinapse_temporal_graph_search` existe por compatibilidade, mas a consulta canÃ´nica Ã© `sinapse_query`. |
| "Tomei uma decisÃ£o ou aprendi um padrÃ£o reutilizÃ¡vel." | `sinapse_save_decision` / `sinapse_save_learning` | Grave na hora; nÃ£o deixe sÃ³ na resposta do chat. |
| "Quero escrever evento temporal bruto." | `sinapse_temporal_save` | SÃ³ grava direto no claude-mem em server-beta; no runtime worker atual, trate como fallback/nota, nÃ£o como caminho principal. |

## 3. Grave na hora (ao decidir, aprender ou decompÃ´r)
| Necessidade | Tool |
|-------------|------|
| DecisÃ£o (escolha entre alternativas + razÃ£o) | `sinapse_save_decision(title, content)` |
| PadrÃ£o/insight/liÃ§Ã£o reaproveitÃ¡vel | `sinapse_save_learning(title, content)` |
| Objetivo grande â†’ passos atÃ´micos (Intent Memory) | `sinapse_plan_goal(goal, context?)` |
| Nota monolÃ­tica (Patterns.md) â†’ notas atÃ´micas Zettelkasten | `sinapse_zettelkasten_split(source_file, output_dir?)` |
| Capturar tela de bug/progresso visual (nÃ£o em loop!) | `sinapse_capture_screen(description, monitor?)` |
| ObservaÃ§Ã£o temporal crua (kind=change/decision/learning/event) | `sinapse_temporal_save(content, kind?)` |

## 4. Consolide ao terminar
- `sinapse_session_end(summary)` â€” atualiza `brain/Current State.md` e
  registra a observaÃ§Ã£o de fechamento no UMC.

## Regras de uso
- **Use SOMENTE as tools `sinapse_*` e `search_memories`.** Nunca chame
  `nmem`, `claude-mem`, `graphify` ou `falkordb` diretamente â€” o sinapse
  jÃ¡ os federa e deduplica via Context Fusion.
- RTK nÃ£o Ã© ferramenta de memÃ³ria nem backend do `sinapse_query`; Ã© apenas a
  camada de otimizaÃ§Ã£o de comandos shell. Quando precisar configurar RTK, use
  `./scripts/services/start-rtk.sh --only <agente>` para o agente/CLI correto.
- `sinapse_query` Ã© o orquestrador canÃ´nico (7 backends). Use-o em vez de
  tools especÃ­ficas de um backend sempre que possÃ­vel.
- `sinapse_temporal_graph_search` estÃ¡ deprecated: mantido para nÃ£o
  quebrar clientes existentes, mas a consulta cerebral canÃ´nica Ã©
  `sinapse_query` (que funde Graphiti junto com os outros 6 Ã³rgÃ£os).
- `sinapse_health()` retorna o status de todos os backends; use para
  diagnÃ³stico quando uma query retornar vazio inesperadamente.
- `sinapse_capture_screen` apenas em pedido explÃ­cito â€” nunca em loop ou
  monitoramento. Requer `description` (motivo) e `monitor` em setups
  multi-monitor.
- `sinapse_zettelkasten_split` requer Ollama local rodando (qwen2.5-coder:3b).
- Consultar antes de agir e gravar o que for reaproveitÃ¡vel nÃ£o Ã© opcional:
  Ã© como o cÃ©rebro do projeto evolui entre sessÃµes.
<!-- END HIVE-MIND SINAPSE -->

<claude-mem-context>
# claude-mem: Cross-Session Memory

*No context yet. Complete your first session and context will appear here.*

Use claude-mem's MCP search tools for manual memory queries.
</claude-mem-context>

<!-- BEGIN HIVE-MIND SINAPSE (auto-managed by register-mcp.ps1 -- do not edit) -->
# Hive-Mind Protocol (sinapse-memory) â€” MANDATORY

You have the 15 `sinapse_*` tools and `search_memories`. This is the working
protocol; always follow it, without exception. The raw backends (NeuralMemory, claude-mem,
Graphify, Graphiti/FalkorDB, UMC, sqlite-vec, filesystem) are federated inside
sinapse via `sinapse_query` (Context Fusion with circuit breaker
and 8s timeout) â€” **never call them directly**.

## 0. Pre-check (once at the start of the session)
- `sinapse_health()` â€” confirm that all backends are operational
  before working. If any fail, report and use `sinapse_temporal_search`
  or `search_memories` in `text` mode as a fallback.

## 1. Recall before acting (at the start of each task)
| Need | Tool |
|------|------|
| Project state/history, decisions, patterns, code/vault, and general context | `sinapse_query("<topic>")` (canonical hybrid search: fuses UMC + NeuralMemory + sqlite-vec + claude-mem + Graphify + Graphiti + filesystem) |
| Recent activity from conversations, prompts, sessions, and raw claude-mem observations | `sinapse_temporal_search("<short specific terms>")` â†’ `sinapse_temporal_timeline(anchor=<id>)` â†’ `sinapse_temporal_get_observations(ids=[...])` |
| Backend health/check | `sinapse_health()` |

**Rule:** never claim anything about the project state/history without having
consulted first.

**How to search without getting lost:**
1. To understand "what happened in the project", start with `sinapse_query`.
   It is tolerant of natural language and crosses all organs of the brain.
2. If you need the recent conversation/prompt/session that originated it, use
   `sinapse_temporal_search` as the **textual index for claude-mem**. Search
   with short terms likely to appear in the actual text. Good examples:
   `"setup-brain modelos"`,
   `"Hive-Mind projeto LLM roles fallback"`, `"Model Configuration Not Persisting"`.
3. If `sinapse_temporal_search` returns empty, do not conclude there is no memory:
   reduce the query to 2â€“5 exact terms, try the title returned by
   `sinapse_query`, or go back to `sinapse_query` to retrieve consolidated context.
4. Do not use long phrases, full questions, or many mixed filters in
   `sinapse_temporal_search`; it is best as a textual/timeline search for
   claude-mem, not as a hybrid orchestrator.
5. For raw temporal memory, follow the native `claude-mem` flow:
   `search â†’ timeline â†’ get_observations`.
   - `sinapse_temporal_search` is the compact index: find IDs/titles.
   - `sinapse_temporal_timeline` shows chronological context around an ID
     or an anchor query.
   - `sinapse_temporal_get_observations` hydrates the full content only for the
     filtered IDs. **Never** hydrate details before filtering; that wastes
     tokens and mixes irrelevant context.

## 2. On-demand recall (during work)
| Need | Tool |
|------|------|
| Neurons/notes by semantic similarity (HNSW + FTS) | `search_memories(query, top_k, project, mode)` |
| Facts/decisions with temporal validity (valid_at/invalid_at edges) | `sinapse_temporal_graph_search("<topic>", num_results)` (deprecated â€” use `sinapse_query`) |
| Textual search in the global claude-mem index (`~/.claude-mem`) | `sinapse_temporal_search("<short terms>")` |
| Chronological context around a temporal result | `sinapse_temporal_timeline(anchor=<id>)` or `sinapse_temporal_timeline(query="<terms>")` |
| Full detail of already-filtered temporal observations | `sinapse_temporal_get_observations(ids=[...])` |
| General hybrid search (all layers; default for project context) | `sinapse_query("<topic>")` |
| Vector query on the LightRAG graph (P4) | `sinapse_rag_query(question, mode?)` |
| Promote pending observations into typed knowledge (K3 intake) | `sinapse_promote_knowledge(limit?, dry_run?, import_claude_mem?, source_ids?, since_epoch?, until_epoch?)` |

### Quick tool selection

| Agent question | Use | Practical note |
|----------------|-----|----------------|
| "What is the project state/history?" | `sinapse_query` | First choice. Crosses vault, UMC, claude-mem, Graphify, Graphiti, sqlite-vec, and filesystem. |
| "Which recent prompt/session talked about this?" | `sinapse_temporal_search` â†’ `sinapse_temporal_timeline` â†’ `sinapse_temporal_get_observations` | Use short/exact terms, pick IDs, read the temporal window, and only then hydrate details. |
| "Which consolidated neurons exist on this topic?" | `search_memories` | Use `project` when you know the project; `mode="text"` for literal search. |
| "I need multi-hop relations between already-indexed entities." | `sinapse_rag_query` | Depends on LightRAG being populated; if it returns empty, fall back to `sinapse_query`. |
| "I need temporal/causal facts from Graphiti." | `sinapse_query` | `sinapse_temporal_graph_search` exists for compatibility, but the canonical brain query is `sinapse_query`. |
| "I made a decision or learned a reusable pattern." | `sinapse_save_decision` / `sinapse_save_learning` | Record immediately; do not leave it only in the chat response. |
| "I want to write a raw temporal event." | `sinapse_temporal_save` | Only writes directly into claude-mem in server-beta; in the current worker runtime, treat as a fallback/note, not the primary write path. |
| "There are pending observations that need to become typed knowledge (neurons/candidates)." | `sinapse_promote_knowledge` | Normalizes pending UMC observations/discoveries/session summaries into typed candidates, preserves raw records, quarantines structural errors, links `observation.neuron_id`. Use `dry_run=true` to classify/count without writing. This is normally run by the Dream Cycle; call it manually only for maintenance or debugging the intake pipeline. |

## 3. Record immediately (when deciding, learning, or decomposing)
| Need | Tool |
|------|------|
| Decision (choice between alternatives + reason) | `sinapse_save_decision(title, content, evidence?)` |
| Reusable pattern/insight/lesson | `sinapse_save_learning(title, content, evidence?)` |
| Large goal â†’ atomic steps (Intent Memory) | `sinapse_plan_goal(goal, context?)` |
| Monolithic note (Patterns.md) â†’ atomic Zettelkasten notes | `sinapse_zettelkasten_split(source_file, output_dir?)` |
| Capture a screenshot of bug/visual progress (not in loop!) | `sinapse_capture_screen(description, monitor?)` |
| Raw temporal observation (kind=change/decision/learning/event) | `sinapse_temporal_save(content, kind?)` |

**Epistemic discipline (verified vs hypothesis):** when saving a decision or
learning, pass `evidence` (the command you ran, the test that passed, the file
you read) whenever the claim was actually verified â€” the note is stamped
`confidence: verified`. Without evidence the note is a `hypothesis`: it still
gets saved, but the RetrievalRouter demotes it in ranking until validated, and
the audit lists it for review. If a hypothesis is later refuted, correct the
note instead of leaving it â€” a refuted hypothesis left in place poisons future
retrieval.

**Review TTL (staleness):** every decision/learning is stamped with
`review_date` and `next_review` (default `REVIEW_TTL_DAYS=90`). Once
`next_review` passes, the RetrievalRouter flags the note `stale` and applies
`HIVE_STALENESS_PENALTY` (default `0.85`) to its ranking score â€” same
demotion mechanism as an unverified hypothesis, but time-based instead of
evidence-based. The note is never deleted or excluded, only demoted. If you
revisit a stale note and it still holds, re-save it (or update it) so its
`next_review` window resets.

## 4. Consolidate when finished
- `sinapse_session_end(summary)` â€” updates `brain/Current State.md` and
  records the closing observation in the UMC.

## Usage rules
- **Use ONLY the `sinapse_*` tools and `search_memories`.** Never call
  `nmem`, `claude-mem`, `graphify`, or `falkordb` directly â€” sinapse
  already federates and deduplicates them via Context Fusion.
- RTK is not a memory tool or a `sinapse_query` backend; it is only the
  shell command optimization layer. When you need to configure RTK, use
  `./scripts/services/start-rtk.sh --only <agent>` for the correct agent/CLI.
- `sinapse_query` is the canonical orchestrator (7 backends). Use it instead of
  backend-specific tools whenever possible.
- `sinapse_temporal_graph_search` is deprecated: kept so as not to
  break existing clients, but the canonical brain query is
  `sinapse_query` (which fuses Graphiti together with the other 6 organs).
- `sinapse_health()` returns the status of all backends; use it for
  diagnosis when a query returns empty unexpectedly.
- `sinapse_capture_screen` only on explicit request â€” never in loop or
  monitoring. Requires `description` (reason) and `monitor` in multi-monitor setups.
- `sinapse_zettelkasten_split` requires local Ollama running (qwen2.5-coder:3b).
- **Vault write enforcement:** on hosts where `setup-vault-enforcement`
  has been applied, `cerebro/` is owned by a dedicated service user and the
  agent only has direct write access to `cerebro/90-intake/`. If a direct
  vault write is denied, `sinapse_save_decision`/`sinapse_save_learning`
  fall back automatically to the intake area â€” this is expected behavior,
  not a failure to report or retry. The Dream Cycle later promotes intake
  content into the vault proper via `sinapse_promote_knowledge`.
- Consulting before acting and recording anything reusable is not optional:
  this is how the project brain evolves between sessions.
<!-- END HIVE-MIND SINAPSE -->

<!-- BEGIN HIVE-MIND SINAPSE (auto-managed by register-mcp.ps1 -- do not edit) -->
# Hive-Mind Protocol (sinapse-memory) â€” MANDATORY

You have the 15 `sinapse_*` tools and `search_memories`. This is the working
protocol; always follow it, without exception. The raw backends (NeuralMemory, claude-mem,
Graphify, Graphiti/FalkorDB, UMC, sqlite-vec, filesystem) are federated inside
sinapse via `sinapse_query` (Context Fusion with circuit breaker
and 8s timeout) â€” **never call them directly**.

## 0. Pre-check (once at the start of the session)
- `sinapse_health()` â€” confirm that all backends are operational
  before working. If any fail, report and use `sinapse_temporal_search`
  or `search_memories` in `text` mode as a fallback.

## 1. Recall before acting (at the start of each task)
| Need | Tool |
|------|------|
| Project state/history, decisions, patterns, code/vault, and general context | `sinapse_query("<topic>")` (canonical hybrid search: fuses UMC + NeuralMemory + sqlite-vec + claude-mem + Graphify + Graphiti + filesystem) |
| Recent activity from conversations, prompts, sessions, and raw claude-mem observations | `sinapse_temporal_search("<short specific terms>")` â†’ `sinapse_temporal_timeline(anchor=<id>)` â†’ `sinapse_temporal_get_observations(ids=[...])` |
| Backend health/check | `sinapse_health()` |

**Rule:** never claim anything about the project state/history without having
consulted first.

**How to search without getting lost:**
1. To understand "what happened in the project", start with `sinapse_query`.
   It is tolerant of natural language and crosses all organs of the brain.
2. If you need the recent conversation/prompt/session that originated it, use
   `sinapse_temporal_search` as the **textual index for claude-mem**. Search
   with short terms likely to appear in the actual text. Good examples:
   `"setup-brain modelos"`,
   `"Hive-Mind projeto LLM roles fallback"`, `"Model Configuration Not Persisting"`.
3. If `sinapse_temporal_search` returns empty, do not conclude there is no memory:
   reduce the query to 2â€“5 exact terms, try the title returned by
   `sinapse_query`, or go back to `sinapse_query` to retrieve consolidated context.
4. Do not use long phrases, full questions, or many mixed filters in
   `sinapse_temporal_search`; it is best as a textual/timeline search for
   claude-mem, not as a hybrid orchestrator.
5. For raw temporal memory, follow the native `claude-mem` flow:
   `search â†’ timeline â†’ get_observations`.
   - `sinapse_temporal_search` is the compact index: find IDs/titles.
   - `sinapse_temporal_timeline` shows chronological context around an ID
     or an anchor query.
   - `sinapse_temporal_get_observations` hydrates the full content only for the
     filtered IDs. **Never** hydrate details before filtering; that wastes
     tokens and mixes irrelevant context.

## 2. On-demand recall (during work)
| Need | Tool |
|------|------|
| Neurons/notes by semantic similarity (HNSW + FTS) | `search_memories(query, top_k, project, mode)` |
| Facts/decisions with temporal validity (valid_at/invalid_at edges) | `sinapse_temporal_graph_search("<topic>", num_results)` (deprecated â€” use `sinapse_query`) |
| Textual search in the global claude-mem index (`~/.claude-mem`) | `sinapse_temporal_search("<short terms>")` |
| Chronological context around a temporal result | `sinapse_temporal_timeline(anchor=<id>)` or `sinapse_temporal_timeline(query="<terms>")` |
| Full detail of already-filtered temporal observations | `sinapse_temporal_get_observations(ids=[...])` |
| General hybrid search (all layers; default for project context) | `sinapse_query("<topic>")` |
| Vector query on the LightRAG graph (P4) | `sinapse_rag_query(question, mode?)` |
| Promote pending observations into typed knowledge (K3 intake) | `sinapse_promote_knowledge(limit?, dry_run?, import_claude_mem?, source_ids?, since_epoch?, until_epoch?)` |

### Quick tool selection

| Agent question | Use | Practical note |
|----------------|-----|----------------|
| "What is the project state/history?" | `sinapse_query` | First choice. Crosses vault, UMC, claude-mem, Graphify, Graphiti, sqlite-vec, and filesystem. |
| "Which recent prompt/session talked about this?" | `sinapse_temporal_search` â†’ `sinapse_temporal_timeline` â†’ `sinapse_temporal_get_observations` | Use short/exact terms, pick IDs, read the temporal window, and only then hydrate details. |
| "Which consolidated neurons exist on this topic?" | `search_memories` | Use `project` when you know the project; `mode="text"` for literal search. |
| "I need multi-hop relations between already-indexed entities." | `sinapse_rag_query` | Depends on LightRAG being populated; if it returns empty, fall back to `sinapse_query`. |
| "I need temporal/causal facts from Graphiti." | `sinapse_query` | `sinapse_temporal_graph_search` exists for compatibility, but the canonical brain query is `sinapse_query`. |
| "I made a decision or learned a reusable pattern." | `sinapse_save_decision` / `sinapse_save_learning` | Record immediately; do not leave it only in the chat response. |
| "I want to write a raw temporal event." | `sinapse_temporal_save` | Only writes directly into claude-mem in server-beta; in the current worker runtime, treat as a fallback/note, not the primary write path. |
| "There are pending observations that need to become typed knowledge (neurons/candidates)." | `sinapse_promote_knowledge` | Normalizes pending UMC observations/discoveries/session summaries into typed candidates, preserves raw records, quarantines structural errors, links `observation.neuron_id`. Use `dry_run=true` to classify/count without writing. This is normally run by the Dream Cycle; call it manually only for maintenance or debugging the intake pipeline. |

## 3. Record immediately (when deciding, learning, or decomposing)
| Need | Tool |
|------|------|
| Decision (choice between alternatives + reason) | `sinapse_save_decision(title, content, evidence?)` |
| Reusable pattern/insight/lesson | `sinapse_save_learning(title, content, evidence?)` |
| Large goal â†’ atomic steps (Intent Memory) | `sinapse_plan_goal(goal, context?)` |
| Monolithic note (Patterns.md) â†’ atomic Zettelkasten notes | `sinapse_zettelkasten_split(source_file, output_dir?)` |
| Capture a screenshot of bug/visual progress (not in loop!) | `sinapse_capture_screen(description, monitor?)` |
| Raw temporal observation (kind=change/decision/learning/event) | `sinapse_temporal_save(content, kind?)` |

**Epistemic discipline (verified vs hypothesis):** when saving a decision or
learning, pass `evidence` (the command you ran, the test that passed, the file
you read) whenever the claim was actually verified â€” the note is stamped
`confidence: verified`. Without evidence the note is a `hypothesis`: it still
gets saved, but the RetrievalRouter demotes it in ranking until validated, and
the audit lists it for review. If a hypothesis is later refuted, correct the
note instead of leaving it â€” a refuted hypothesis left in place poisons future
retrieval.

**Review TTL (staleness):** every decision/learning is stamped with
`review_date` and `next_review` (default `REVIEW_TTL_DAYS=90`). Once
`next_review` passes, the RetrievalRouter flags the note `stale` and applies
`HIVE_STALENESS_PENALTY` (default `0.85`) to its ranking score â€” same
demotion mechanism as an unverified hypothesis, but time-based instead of
evidence-based. The note is never deleted or excluded, only demoted. If you
revisit a stale note and it still holds, re-save it (or update it) so its
`next_review` window resets.

## 4. Consolidate when finished
- `sinapse_session_end(summary)` â€” updates `brain/Current State.md` and
  records the closing observation in the UMC.

## Usage rules
- **Use ONLY the `sinapse_*` tools and `search_memories`.** Never call
  `nmem`, `claude-mem`, `graphify`, or `falkordb` directly â€” sinapse
  already federates and deduplicates them via Context Fusion.
- RTK is not a memory tool or a `sinapse_query` backend; it is only the
  shell command optimization layer. When you need to configure RTK, use
  `./scripts/services/start-rtk.sh --only <agent>` for the correct agent/CLI.
- `sinapse_query` is the canonical orchestrator (7 backends). Use it instead of
  backend-specific tools whenever possible.
- `sinapse_temporal_graph_search` is deprecated: kept so as not to
  break existing clients, but the canonical brain query is
  `sinapse_query` (which fuses Graphiti together with the other 6 organs).
- `sinapse_health()` returns the status of all backends; use it for
  diagnosis when a query returns empty unexpectedly.
- `sinapse_capture_screen` only on explicit request â€” never in loop or
  monitoring. Requires `description` (reason) and `monitor` in multi-monitor setups.
- `sinapse_zettelkasten_split` requires local Ollama running (qwen2.5-coder:3b).
- **Vault write enforcement:** on hosts where `setup-vault-enforcement`
  has been applied, `cerebro/` is owned by a dedicated service user and the
  agent only has direct write access to `cerebro/90-intake/`. If a direct
  vault write is denied, `sinapse_save_decision`/`sinapse_save_learning`
  fall back automatically to the intake area â€” this is expected behavior,
  not a failure to report or retry. The Dream Cycle later promotes intake
  content into the vault proper via `sinapse_promote_knowledge`.
- Consulting before acting and recording anything reusable is not optional:
  this is how the project brain evolves between sessions.
<!-- END HIVE-MIND SINAPSE -->

<!-- BEGIN HIVE-MIND SINAPSE (auto-managed by register-mcp.ps1 -- do not edit) -->
# Hive-Mind Protocol (sinapse-memory) â€” MANDATORY

You have the 15 `sinapse_*` tools and `search_memories`. This is the working
protocol; always follow it, without exception. The raw backends (NeuralMemory, claude-mem,
Graphify, Graphiti/FalkorDB, UMC, sqlite-vec, filesystem) are federated inside
sinapse via `sinapse_query` (Context Fusion with circuit breaker
and 8s timeout) â€” **never call them directly**.

## 0. Pre-check (once at the start of the session)
- `sinapse_health()` â€” confirm that all backends are operational
  before working. If any fail, report and use `sinapse_temporal_search`
  or `search_memories` in `text` mode as a fallback.

## 1. Recall before acting (at the start of each task)
| Need | Tool |
|------|------|
| Project state/history, decisions, patterns, code/vault, and general context | `sinapse_query("<topic>")` (canonical hybrid search: fuses UMC + NeuralMemory + sqlite-vec + claude-mem + Graphify + Graphiti + filesystem) |
| Recent activity from conversations, prompts, sessions, and raw claude-mem observations | `sinapse_temporal_search("<short specific terms>")` â†’ `sinapse_temporal_timeline(anchor=<id>)` â†’ `sinapse_temporal_get_observations(ids=[...])` |
| Backend health/check | `sinapse_health()` |

**Rule:** never claim anything about the project state/history without having
consulted first.

**How to search without getting lost:**
1. To understand "what happened in the project", start with `sinapse_query`.
   It is tolerant of natural language and crosses all organs of the brain.
2. If you need the recent conversation/prompt/session that originated it, use
   `sinapse_temporal_search` as the **textual index for claude-mem**. Search
   with short terms likely to appear in the actual text. Good examples:
   `"setup-brain modelos"`,
   `"Hive-Mind projeto LLM roles fallback"`, `"Model Configuration Not Persisting"`.
3. If `sinapse_temporal_search` returns empty, do not conclude there is no memory:
   reduce the query to 2â€“5 exact terms, try the title returned by
   `sinapse_query`, or go back to `sinapse_query` to retrieve consolidated context.
4. Do not use long phrases, full questions, or many mixed filters in
   `sinapse_temporal_search`; it is best as a textual/timeline search for
   claude-mem, not as a hybrid orchestrator.
5. For raw temporal memory, follow the native `claude-mem` flow:
   `search â†’ timeline â†’ get_observations`.
   - `sinapse_temporal_search` is the compact index: find IDs/titles.
   - `sinapse_temporal_timeline` shows chronological context around an ID
     or an anchor query.
   - `sinapse_temporal_get_observations` hydrates the full content only for the
     filtered IDs. **Never** hydrate details before filtering; that wastes
     tokens and mixes irrelevant context.

## 2. On-demand recall (during work)
| Need | Tool |
|------|------|
| Neurons/notes by semantic similarity (HNSW + FTS) | `search_memories(query, top_k, project, mode)` |
| Facts/decisions with temporal validity (valid_at/invalid_at edges) | `sinapse_temporal_graph_search("<topic>", num_results)` (deprecated â€” use `sinapse_query`) |
| Textual search in the global claude-mem index (`~/.claude-mem`) | `sinapse_temporal_search("<short terms>")` |
| Chronological context around a temporal result | `sinapse_temporal_timeline(anchor=<id>)` or `sinapse_temporal_timeline(query="<terms>")` |
| Full detail of already-filtered temporal observations | `sinapse_temporal_get_observations(ids=[...])` |
| General hybrid search (all layers; default for project context) | `sinapse_query("<topic>")` |
| Vector query on the LightRAG graph (P4) | `sinapse_rag_query(question, mode?)` |
| Promote pending observations into typed knowledge (K3 intake) | `sinapse_promote_knowledge(limit?, dry_run?, import_claude_mem?, source_ids?, since_epoch?, until_epoch?)` |

### Quick tool selection

| Agent question | Use | Practical note |
|----------------|-----|----------------|
| "What is the project state/history?" | `sinapse_query` | First choice. Crosses vault, UMC, claude-mem, Graphify, Graphiti, sqlite-vec, and filesystem. |
| "Which recent prompt/session talked about this?" | `sinapse_temporal_search` â†’ `sinapse_temporal_timeline` â†’ `sinapse_temporal_get_observations` | Use short/exact terms, pick IDs, read the temporal window, and only then hydrate details. |
| "Which consolidated neurons exist on this topic?" | `search_memories` | Use `project` when you know the project; `mode="text"` for literal search. |
| "I need multi-hop relations between already-indexed entities." | `sinapse_rag_query` | Depends on LightRAG being populated; if it returns empty, fall back to `sinapse_query`. |
| "I need temporal/causal facts from Graphiti." | `sinapse_query` | `sinapse_temporal_graph_search` exists for compatibility, but the canonical brain query is `sinapse_query`. |
| "I made a decision or learned a reusable pattern." | `sinapse_save_decision` / `sinapse_save_learning` | Record immediately; do not leave it only in the chat response. |
| "I want to write a raw temporal event." | `sinapse_temporal_save` | Only writes directly into claude-mem in server-beta; in the current worker runtime, treat as a fallback/note, not the primary write path. |
| "There are pending observations that need to become typed knowledge (neurons/candidates)." | `sinapse_promote_knowledge` | Normalizes pending UMC observations/discoveries/session summaries into typed candidates, preserves raw records, quarantines structural errors, links `observation.neuron_id`. Use `dry_run=true` to classify/count without writing. This is normally run by the Dream Cycle; call it manually only for maintenance or debugging the intake pipeline. |

## 3. Record immediately (when deciding, learning, or decomposing)
| Need | Tool |
|------|------|
| Decision (choice between alternatives + reason) | `sinapse_save_decision(title, content, evidence?)` |
| Reusable pattern/insight/lesson | `sinapse_save_learning(title, content, evidence?)` |
| Large goal â†’ atomic steps (Intent Memory) | `sinapse_plan_goal(goal, context?)` |
| Monolithic note (Patterns.md) â†’ atomic Zettelkasten notes | `sinapse_zettelkasten_split(source_file, output_dir?)` |
| Capture a screenshot of bug/visual progress (not in loop!) | `sinapse_capture_screen(description, monitor?)` |
| Raw temporal observation (kind=change/decision/learning/event) | `sinapse_temporal_save(content, kind?)` |

**Epistemic discipline (verified vs hypothesis):** when saving a decision or
learning, pass `evidence` (the command you ran, the test that passed, the file
you read) whenever the claim was actually verified â€” the note is stamped
`confidence: verified`. Without evidence the note is a `hypothesis`: it still
gets saved, but the RetrievalRouter demotes it in ranking until validated, and
the audit lists it for review. If a hypothesis is later refuted, correct the
note instead of leaving it â€” a refuted hypothesis left in place poisons future
retrieval.

**Review TTL (staleness):** every decision/learning is stamped with
`review_date` and `next_review` (default `REVIEW_TTL_DAYS=90`). Once
`next_review` passes, the RetrievalRouter flags the note `stale` and applies
`HIVE_STALENESS_PENALTY` (default `0.85`) to its ranking score â€” same
demotion mechanism as an unverified hypothesis, but time-based instead of
evidence-based. The note is never deleted or excluded, only demoted. If you
revisit a stale note and it still holds, re-save it (or update it) so its
`next_review` window resets.

## 4. Consolidate when finished
- `sinapse_session_end(summary)` â€” updates `brain/Current State.md` and
  records the closing observation in the UMC.

## Usage rules
- **Use ONLY the `sinapse_*` tools and `search_memories`.** Never call
  `nmem`, `claude-mem`, `graphify`, or `falkordb` directly â€” sinapse
  already federates and deduplicates them via Context Fusion.
- RTK is not a memory tool or a `sinapse_query` backend; it is only the
  shell command optimization layer. When you need to configure RTK, use
  `./scripts/services/start-rtk.sh --only <agent>` for the correct agent/CLI.
- `sinapse_query` is the canonical orchestrator (7 backends). Use it instead of
  backend-specific tools whenever possible.
- `sinapse_temporal_graph_search` is deprecated: kept so as not to
  break existing clients, but the canonical brain query is
  `sinapse_query` (which fuses Graphiti together with the other 6 organs).
- `sinapse_health()` returns the status of all backends; use it for
  diagnosis when a query returns empty unexpectedly.
- `sinapse_capture_screen` only on explicit request â€” never in loop or
  monitoring. Requires `description` (reason) and `monitor` in multi-monitor setups.
- `sinapse_zettelkasten_split` requires local Ollama running (qwen2.5-coder:3b).
- **Vault write enforcement:** on hosts where `setup-vault-enforcement`
  has been applied, `cerebro/` is owned by a dedicated service user and the
  agent only has direct write access to `cerebro/90-intake/`. If a direct
  vault write is denied, `sinapse_save_decision`/`sinapse_save_learning`
  fall back automatically to the intake area â€” this is expected behavior,
  not a failure to report or retry. The Dream Cycle later promotes intake
  content into the vault proper via `sinapse_promote_knowledge`.
- Consulting before acting and recording anything reusable is not optional:
  this is how the project brain evolves between sessions.
<!-- END HIVE-MIND SINAPSE -->

<!-- BEGIN HIVE-MIND SINAPSE (auto-managed by register-mcp.ps1 -- do not edit) -->
# Hive-Mind Protocol (sinapse-memory) â€” MANDATORY

You have the 15 `sinapse_*` tools and `search_memories`. This is the working
protocol; always follow it, without exception. The raw backends (NeuralMemory, claude-mem,
Graphify, Graphiti/FalkorDB, UMC, sqlite-vec, filesystem) are federated inside
sinapse via `sinapse_query` (Context Fusion with circuit breaker
and 8s timeout) â€” **never call them directly**.

## 0. Pre-check (once at the start of the session)
- `sinapse_health()` â€” confirm that all backends are operational
  before working. If any fail, report and use `sinapse_temporal_search`
  or `search_memories` in `text` mode as a fallback.

## 1. Recall before acting (at the start of each task)
| Need | Tool |
|------|------|
| Project state/history, decisions, patterns, code/vault, and general context | `sinapse_query("<topic>")` (canonical hybrid search: fuses UMC + NeuralMemory + sqlite-vec + claude-mem + Graphify + Graphiti + filesystem) |
| Recent activity from conversations, prompts, sessions, and raw claude-mem observations | `sinapse_temporal_search("<short specific terms>")` â†’ `sinapse_temporal_timeline(anchor=<id>)` â†’ `sinapse_temporal_get_observations(ids=[...])` |
| Backend health/check | `sinapse_health()` |

**Rule:** never claim anything about the project state/history without having
consulted first.

**How to search without getting lost:**
1. To understand "what happened in the project", start with `sinapse_query`.
   It is tolerant of natural language and crosses all organs of the brain.
2. If you need the recent conversation/prompt/session that originated it, use
   `sinapse_temporal_search` as the **textual index for claude-mem**. Search
   with short terms likely to appear in the actual text. Good examples:
   `"setup-brain modelos"`,
   `"Hive-Mind projeto LLM roles fallback"`, `"Model Configuration Not Persisting"`.
3. If `sinapse_temporal_search` returns empty, do not conclude there is no memory:
   reduce the query to 2â€“5 exact terms, try the title returned by
   `sinapse_query`, or go back to `sinapse_query` to retrieve consolidated context.
4. Do not use long phrases, full questions, or many mixed filters in
   `sinapse_temporal_search`; it is best as a textual/timeline search for
   claude-mem, not as a hybrid orchestrator.
5. For raw temporal memory, follow the native `claude-mem` flow:
   `search â†’ timeline â†’ get_observations`.
   - `sinapse_temporal_search` is the compact index: find IDs/titles.
   - `sinapse_temporal_timeline` shows chronological context around an ID
     or an anchor query.
   - `sinapse_temporal_get_observations` hydrates the full content only for the
     filtered IDs. **Never** hydrate details before filtering; that wastes
     tokens and mixes irrelevant context.

## 2. On-demand recall (during work)
| Need | Tool |
|------|------|
| Neurons/notes by semantic similarity (HNSW + FTS) | `search_memories(query, top_k, project, mode)` |
| Facts/decisions with temporal validity (valid_at/invalid_at edges) | `sinapse_temporal_graph_search("<topic>", num_results)` (deprecated â€” use `sinapse_query`) |
| Textual search in the global claude-mem index (`~/.claude-mem`) | `sinapse_temporal_search("<short terms>")` |
| Chronological context around a temporal result | `sinapse_temporal_timeline(anchor=<id>)` or `sinapse_temporal_timeline(query="<terms>")` |
| Full detail of already-filtered temporal observations | `sinapse_temporal_get_observations(ids=[...])` |
| General hybrid search (all layers; default for project context) | `sinapse_query("<topic>")` |
| Vector query on the LightRAG graph (P4) | `sinapse_rag_query(question, mode?)` |
| Promote pending observations into typed knowledge (K3 intake) | `sinapse_promote_knowledge(limit?, dry_run?, import_claude_mem?, source_ids?, since_epoch?, until_epoch?)` |

### Quick tool selection

| Agent question | Use | Practical note |
|----------------|-----|----------------|
| "What is the project state/history?" | `sinapse_query` | First choice. Crosses vault, UMC, claude-mem, Graphify, Graphiti, sqlite-vec, and filesystem. |
| "Which recent prompt/session talked about this?" | `sinapse_temporal_search` â†’ `sinapse_temporal_timeline` â†’ `sinapse_temporal_get_observations` | Use short/exact terms, pick IDs, read the temporal window, and only then hydrate details. |
| "Which consolidated neurons exist on this topic?" | `search_memories` | Use `project` when you know the project; `mode="text"` for literal search. |
| "I need multi-hop relations between already-indexed entities." | `sinapse_rag_query` | Depends on LightRAG being populated; if it returns empty, fall back to `sinapse_query`. |
| "I need temporal/causal facts from Graphiti." | `sinapse_query` | `sinapse_temporal_graph_search` exists for compatibility, but the canonical brain query is `sinapse_query`. |
| "I made a decision or learned a reusable pattern." | `sinapse_save_decision` / `sinapse_save_learning` | Record immediately; do not leave it only in the chat response. |
| "I want to write a raw temporal event." | `sinapse_temporal_save` | Only writes directly into claude-mem in server-beta; in the current worker runtime, treat as a fallback/note, not the primary write path. |
| "There are pending observations that need to become typed knowledge (neurons/candidates)." | `sinapse_promote_knowledge` | Normalizes pending UMC observations/discoveries/session summaries into typed candidates, preserves raw records, quarantines structural errors, links `observation.neuron_id`. Use `dry_run=true` to classify/count without writing. This is normally run by the Dream Cycle; call it manually only for maintenance or debugging the intake pipeline. |

## 3. Record immediately (when deciding, learning, or decomposing)
| Need | Tool |
|------|------|
| Decision (choice between alternatives + reason) | `sinapse_save_decision(title, content, evidence?)` |
| Reusable pattern/insight/lesson | `sinapse_save_learning(title, content, evidence?)` |
| Large goal â†’ atomic steps (Intent Memory) | `sinapse_plan_goal(goal, context?)` |
| Monolithic note (Patterns.md) â†’ atomic Zettelkasten notes | `sinapse_zettelkasten_split(source_file, output_dir?)` |
| Capture a screenshot of bug/visual progress (not in loop!) | `sinapse_capture_screen(description, monitor?)` |
| Raw temporal observation (kind=change/decision/learning/event) | `sinapse_temporal_save(content, kind?)` |

**Epistemic discipline (verified vs hypothesis):** when saving a decision or
learning, pass `evidence` (the command you ran, the test that passed, the file
you read) whenever the claim was actually verified â€” the note is stamped
`confidence: verified`. Without evidence the note is a `hypothesis`: it still
gets saved, but the RetrievalRouter demotes it in ranking until validated, and
the audit lists it for review. If a hypothesis is later refuted, correct the
note instead of leaving it â€” a refuted hypothesis left in place poisons future
retrieval.

**Review TTL (staleness):** every decision/learning is stamped with
`review_date` and `next_review` (default `REVIEW_TTL_DAYS=90`). Once
`next_review` passes, the RetrievalRouter flags the note `stale` and applies
`HIVE_STALENESS_PENALTY` (default `0.85`) to its ranking score â€” same
demotion mechanism as an unverified hypothesis, but time-based instead of
evidence-based. The note is never deleted or excluded, only demoted. If you
revisit a stale note and it still holds, re-save it (or update it) so its
`next_review` window resets.

## 4. Consolidate when finished
- `sinapse_session_end(summary)` â€” updates `brain/Current State.md` and
  records the closing observation in the UMC.

## Usage rules
- **Use ONLY the `sinapse_*` tools and `search_memories`.** Never call
  `nmem`, `claude-mem`, `graphify`, or `falkordb` directly â€” sinapse
  already federates and deduplicates them via Context Fusion.
- RTK is not a memory tool or a `sinapse_query` backend; it is only the
  shell command optimization layer. When you need to configure RTK, use
  `./scripts/services/start-rtk.sh --only <agent>` for the correct agent/CLI.
- `sinapse_query` is the canonical orchestrator (7 backends). Use it instead of
  backend-specific tools whenever possible.
- `sinapse_temporal_graph_search` is deprecated: kept so as not to
  break existing clients, but the canonical brain query is
  `sinapse_query` (which fuses Graphiti together with the other 6 organs).
- `sinapse_health()` returns the status of all backends; use it for
  diagnosis when a query returns empty unexpectedly.
- `sinapse_capture_screen` only on explicit request â€” never in loop or
  monitoring. Requires `description` (reason) and `monitor` in multi-monitor setups.
- `sinapse_zettelkasten_split` requires local Ollama running (qwen2.5-coder:3b).
- **Vault write enforcement:** on hosts where `setup-vault-enforcement`
  has been applied, `cerebro/` is owned by a dedicated service user and the
  agent only has direct write access to `cerebro/90-intake/`. If a direct
  vault write is denied, `sinapse_save_decision`/`sinapse_save_learning`
  fall back automatically to the intake area â€” this is expected behavior,
  not a failure to report or retry. The Dream Cycle later promotes intake
  content into the vault proper via `sinapse_promote_knowledge`.
- Consulting before acting and recording anything reusable is not optional:
  this is how the project brain evolves between sessions.
<!-- END HIVE-MIND SINAPSE -->

