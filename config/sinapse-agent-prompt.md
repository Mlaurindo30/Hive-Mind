# Protocolo Hive-Mind (sinapse-memory) — OBRIGATÓRIO

Você tem as 13 tools `sinapse_*` e `search_memories`. Este é o protocolo de
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
| Estado/histórico do projeto, decisões, padrões | `sinapse_query("<tema>")` (funde 7 backends: UMC + NeuralMemory + sqlite-vec + claude-mem + Graphify + Graphiti + filesystem) |
| Atividade das últimas sessões (timeline, eventos) | `sinapse_temporal_search("<tema>")` |
| Saúde/verificação de backends | `sinapse_health()` |

**Regra:** nunca afirme nada sobre o estado/histórico do projeto sem ter
consultado antes.

## 2. Recall sob demanda (durante o trabalho)
| Necessidade | Tool |
|-------------|------|
| Neurônios/notas por similaridade semântica (HNSW + FTS) | `search_memories(query, top_k, project, mode)` |
| Fatos/decisões com validade temporal (arestas valid_at/invalid_at) | `sinapse_temporal_graph_search("<tema>", num_results)` (deprecated — use `sinapse_query`) |
| Busca direta na camada temporal (FTS5 + Chroma) | `sinapse_temporal_search("<tema>")` |
| Busca híbrida geral (todas as camadas) | `sinapse_query("<tema>")` |
| Consulta vetorial no grafo LightRAG (P4) | `sinapse_rag_query(question, mode?)` |

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
