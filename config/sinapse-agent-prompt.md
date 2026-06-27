# Protocolo Hive-Mind (sinapse-memory) — OBRIGATÓRIO

Você tem as 15 tools `sinapse_*` e `search_memories`. Este é o protocolo de
trabalho; siga sempre, sem exceção. Os backends crus (NeuralMemory, claude-mem,
Graphify, Graphiti/FalkorDB, UMC, sqlite-vec, filesystem) são federados por
dentro do sinapse via `sinapse_query` (Context Fusion com circuit breaker
e timeout 8s) — **nunca os chame diretamente**.

## 0. Pré-checagem (uma vez no início da sessão)
- `sinapse_health()` — confirme que todos os backends estão operacionais
  antes de trabalhar. Se algum falhar, reporte e use `sinapse_temporal_search`
  ou `search_memories` no modo `text` como fallback.

## 1. Recupere antes de agir (no início de cada tarefa)
| Necessidade | Tool |
|-------------|------|
| Estado/histórico do projeto, decisões, padrões, código/vault e contexto geral | `sinapse_query("<tema>")` (busca híbrida canônica: funde UMC + NeuralMemory + sqlite-vec + claude-mem + Graphify + Graphiti + filesystem) |
| Atividade recente de conversas, prompts, sessões e observações brutas do claude-mem | `sinapse_temporal_search("<termos curtos e específicos>")` → `sinapse_temporal_timeline(anchor=<id>)` → `sinapse_temporal_get_observations(ids=[...])` |
| Saúde/verificação de backends | `sinapse_health()` |

**Regra:** nunca afirme nada sobre o estado/histórico do projeto sem ter
consultado antes.

**Como pesquisar sem se perder:**
1. Para entender "o que aconteceu no projeto", comece com `sinapse_query`.
   Ele é tolerante a linguagem natural e cruza todos os órgãos do cérebro.
2. Se precisar da conversa/prompt/sessão recente que originou aquilo, use
   `sinapse_temporal_search` como **índice textual do claude-mem**. Pesquise
   com termos curtos que provavelmente estão no texto real. Exemplos bons:
   `"setup-brain modelos"`,
   `"Hive-Mind projeto LLM roles fallback"`, `"Model Configuration Not Persisting"`.
3. Se `sinapse_temporal_search` vier vazio, não conclua que não existe memória:
   reduza a consulta para 2-5 termos exatos, tente o título retornado por
   `sinapse_query`, ou volte para `sinapse_query` para recuperar contexto
   consolidado.
4. Não use frases longas, perguntas completas ou muitos filtros misturados em
   `sinapse_temporal_search`; ela é melhor como busca textual/timeline do
   claude-mem, não como orquestrador híbrido.
5. Para memória temporal bruta, siga o fluxo nativo do `claude-mem`:
   `search → timeline → get_observations`.
   - `sinapse_temporal_search` é o índice compacto: encontre IDs/títulos.
   - `sinapse_temporal_timeline` mostra contexto cronológico ao redor de um ID
     ou de uma query-âncora.
   - `sinapse_temporal_get_observations` hidrata o conteúdo completo apenas dos
     IDs filtrados. **Nunca** hidrate detalhes antes de filtrar; isso desperdiça
     tokens e mistura contexto irrelevante.

## 2. Recall sob demanda (durante o trabalho)
| Necessidade | Tool |
|-------------|------|
| Neurônios/notas por similaridade semântica (HNSW + FTS) | `search_memories(query, top_k, project, mode)` |
| Fatos/decisões com validade temporal (arestas valid_at/invalid_at) | `sinapse_temporal_graph_search("<tema>", num_results)` (deprecated — use `sinapse_query`) |
| Busca textual no índice do claude-mem global (`~/.claude-mem`) | `sinapse_temporal_search("<termos curtos>")` |
| Contexto cronológico ao redor de um resultado temporal | `sinapse_temporal_timeline(anchor=<id>)` ou `sinapse_temporal_timeline(query="<termos>")` |
| Detalhe completo de observações temporais já filtradas | `sinapse_temporal_get_observations(ids=[...])` |
| Busca híbrida geral (todas as camadas; padrão para contexto do projeto) | `sinapse_query("<tema>")` |
| Consulta vetorial no grafo LightRAG (P4) | `sinapse_rag_query(question, mode?)` |

### Escolha rápida das tools

| Pergunta do agente | Use | Observação prática |
|--------------------|-----|--------------------|
| "Qual é o estado/histórico do projeto?" | `sinapse_query` | Primeira escolha. Cruza vault, UMC, claude-mem, Graphify, Graphiti, sqlite-vec e filesystem. |
| "Qual prompt/sessão recente falou disso?" | `sinapse_temporal_search` → `sinapse_temporal_timeline` → `sinapse_temporal_get_observations` | Use termos curtos/exatos, escolha IDs, leia a janela temporal e só então hidrate detalhes. |
| "Quais neurônios consolidados existem sobre esse tema?" | `search_memories` | Use `project` quando souber o projeto; `mode="text"` para busca literal. |
| "Preciso de relações multi-hop entre entidades já indexadas." | `sinapse_rag_query` | Depende do LightRAG estar populado; se vier vazio, volte para `sinapse_query`. |
| "Preciso de fatos temporais/causais do Graphiti." | `sinapse_query` | `sinapse_temporal_graph_search` existe por compatibilidade, mas a consulta canônica é `sinapse_query`. |
| "Tomei uma decisão ou aprendi um padrão reutilizável." | `sinapse_save_decision` / `sinapse_save_learning` | Grave na hora; não deixe só na resposta do chat. |
| "Quero escrever evento temporal bruto." | `sinapse_temporal_save` | Só grava direto no claude-mem em server-beta; no runtime worker atual, trate como fallback/nota, não como caminho principal. |

## 3. Grave na hora (ao decidir, aprender ou decompôr)
| Necessidade | Tool |
|-------------|------|
| Decisão (escolha entre alternativas + razão) | `sinapse_save_decision(title, content)` |
| Padrão/insight/lição reaproveitável | `sinapse_save_learning(title, content)` |
| Objetivo grande → passos atômicos (Intent Memory) | `sinapse_plan_goal(goal, context?)` |
| Nota monolítica (Patterns.md) → notas atômicas Zettelkasten | `sinapse_zettelkasten_split(source_file, output_dir?)` |
| Capturar tela de bug/progresso visual (não em loop!) | `sinapse_capture_screen(description, monitor?)` |
| Observação temporal crua (kind=change/decision/learning/event) | `sinapse_temporal_save(content, kind?)` |

## 4. Consolide ao terminar
- `sinapse_session_end(summary)` — atualiza `brain/Current State.md` e
  registra a observação de fechamento no UMC.

## Regras de uso
- **Use SOMENTE as tools `sinapse_*` e `search_memories`.** Nunca chame
  `nmem`, `claude-mem`, `graphify` ou `falkordb` diretamente — o sinapse
  já os federa e deduplica via Context Fusion.
- RTK não é ferramenta de memória nem backend do `sinapse_query`; é apenas a
  camada de otimização de comandos shell. Quando precisar configurar RTK, use
  `./scripts/services/start-rtk.sh --only <agente>` para o agente/CLI correto.
- `sinapse_query` é o orquestrador canônico (7 backends). Use-o em vez de
  tools específicas de um backend sempre que possível.
- `sinapse_temporal_graph_search` está deprecated: mantido para não
  quebrar clientes existentes, mas a consulta cerebral canônica é
  `sinapse_query` (que funde Graphiti junto com os outros 6 órgãos).
- `sinapse_health()` retorna o status de todos os backends; use para
  diagnóstico quando uma query retornar vazio inesperadamente.
- `sinapse_capture_screen` apenas em pedido explícito — nunca em loop ou
  monitoramento. Requer `description` (motivo) e `monitor` em setups
  multi-monitor.
- `sinapse_zettelkasten_split` requer Ollama local rodando (qwen2.5-coder:3b).
- Consultar antes de agir e gravar o que for reaproveitável não é opcional:
  é como o cérebro do projeto evolui entre sessões.
