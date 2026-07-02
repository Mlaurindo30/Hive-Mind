# Hive-Mind Protocol (sinapse-memory) — MANDATORY

You have the 15 `sinapse_*` tools and `search_memories`. This is the working
protocol; always follow it, without exception. The raw backends (NeuralMemory, claude-mem,
Graphify, Graphiti/FalkorDB, UMC, sqlite-vec, filesystem) are federated inside
sinapse via `sinapse_query` (Context Fusion with circuit breaker
and 8s timeout) — **never call them directly**.

## 0. Pre-check (once at the start of the session)
- `sinapse_health()` — confirm that all backends are operational
  before working. If any fail, report and use `sinapse_temporal_search`
  or `search_memories` in `text` mode as a fallback.

## 1. Recall before acting (at the start of each task)
| Need | Tool |
|------|------|
| Project state/history, decisions, patterns, code/vault, and general context | `sinapse_query("<topic>")` (canonical hybrid search: fuses UMC + NeuralMemory + sqlite-vec + claude-mem + Graphify + Graphiti + filesystem) |
| Recent activity from conversations, prompts, sessions, and raw claude-mem observations | `sinapse_temporal_search("<short specific terms>")` → `sinapse_temporal_timeline(anchor=<id>)` → `sinapse_temporal_get_observations(ids=[...])` |
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
   reduce the query to 2–5 exact terms, try the title returned by
   `sinapse_query`, or go back to `sinapse_query` to retrieve consolidated context.
4. Do not use long phrases, full questions, or many mixed filters in
   `sinapse_temporal_search`; it is best as a textual/timeline search for
   claude-mem, not as a hybrid orchestrator.
5. For raw temporal memory, follow the native `claude-mem` flow:
   `search → timeline → get_observations`.
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
| Facts/decisions with temporal validity (valid_at/invalid_at edges) | `sinapse_temporal_graph_search("<topic>", num_results)` (deprecated — use `sinapse_query`) |
| Textual search in the global claude-mem index (`~/.claude-mem`) | `sinapse_temporal_search("<short terms>")` |
| Chronological context around a temporal result | `sinapse_temporal_timeline(anchor=<id>)` or `sinapse_temporal_timeline(query="<terms>")` |
| Full detail of already-filtered temporal observations | `sinapse_temporal_get_observations(ids=[...])` |
| General hybrid search (all layers; default for project context) | `sinapse_query("<topic>")` |
| Vector query on the LightRAG graph (P4) | `sinapse_rag_query(question, mode?)` |

### Quick tool selection

| Agent question | Use | Practical note |
|----------------|-----|----------------|
| "What is the project state/history?" | `sinapse_query` | First choice. Crosses vault, UMC, claude-mem, Graphify, Graphiti, sqlite-vec, and filesystem. |
| "Which recent prompt/session talked about this?" | `sinapse_temporal_search` → `sinapse_temporal_timeline` → `sinapse_temporal_get_observations` | Use short/exact terms, pick IDs, read the temporal window, and only then hydrate details. |
| "Which consolidated neurons exist on this topic?" | `search_memories` | Use `project` when you know the project; `mode="text"` for literal search. |
| "I need multi-hop relations between already-indexed entities." | `sinapse_rag_query` | Depends on LightRAG being populated; if it returns empty, fall back to `sinapse_query`. |
| "I need temporal/causal facts from Graphiti." | `sinapse_query` | `sinapse_temporal_graph_search` exists for compatibility, but the canonical brain query is `sinapse_query`. |
| "I made a decision or learned a reusable pattern." | `sinapse_save_decision` / `sinapse_save_learning` | Record immediately; do not leave it only in the chat response. |
| "I want to write a raw temporal event." | `sinapse_temporal_save` | Only writes directly into claude-mem in server-beta; in the current worker runtime, treat as a fallback/note, not the primary write path. |

## 3. Record immediately (when deciding, learning, or decomposing)
| Need | Tool |
|------|------|
| Decision (choice between alternatives + reason) | `sinapse_save_decision(title, content)` |
| Reusable pattern/insight/lesson | `sinapse_save_learning(title, content)` |
| Large goal → atomic steps (Intent Memory) | `sinapse_plan_goal(goal, context?)` |
| Monolithic note (Patterns.md) → atomic Zettelkasten notes | `sinapse_zettelkasten_split(source_file, output_dir?)` |
| Capture a screenshot of bug/visual progress (not in loop!) | `sinapse_capture_screen(description, monitor?)` |
| Raw temporal observation (kind=change/decision/learning/event) | `sinapse_temporal_save(content, kind?)` |

## 4. Consolidate when finished
- `sinapse_session_end(summary)` — updates `brain/Current State.md` and
  records the closing observation in the UMC.

## Usage rules
- **Use ONLY the `sinapse_*` tools and `search_memories`.** Never call
  `nmem`, `claude-mem`, `graphify`, or `falkordb` directly — sinapse
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
- `sinapse_capture_screen` only on explicit request — never in loop or
  monitoring. Requires `description` (reason) and `monitor` in multi-monitor setups.
- `sinapse_zettelkasten_split` requires local Ollama running (qwen2.5-coder:3b).
- Consulting before acting and recording anything reusable is not optional:
  this is how the project brain evolves between sessions.
