# Documento de Implementação — Hive-Mind

## 1. Resumo executivo
O projeto **Hive-Mind** é a evolução do Sinapse Agent. O objetivo é criar uma camada de memória universal e persistente para agentes de IA, utilizando um único banco de dados SQLite centralizado (UMC) que integra as dimensões Estrutural (Grafos), Temporal (Logs) e Associativa (Vetores). O estado atual é de fragmentação entre JSON, SQLite e Chroma. O resultado esperado é uma redução drástica na latência de consulta, maior consistência de dados e uma integração visual rica através do Obsidian.

## 2. Escopo da implementação

### Obrigatório para MVP (Fases 1 e 2) - CONCLUÍDO
- [x] Criação do banco de dados unificado SQLite com suporte a `sqlite-vec` e `FTS5`.
- [x] Refatoração do **Graphify** para indexar o vault diretamente no SQLite.
- [x] Motor de busca híbrido (Texto + Vetor + Grafo) em uma única interface SQL.
- [x] Plugin de leitura unificado para o agente Hermes.

### Recomendado para versão beta (Fases 3 e 4) - CONCLUÍDO
- [x] Migração total dos logs do **claude-mem** para o banco UMC.
- [x] Servidor MCP unificado expondo o UMC para agentes externos (Cursor, Claude Code).
- [x] Dashboard de visualização no Obsidian via plugin SQLite.
- [x] Integração de Logs do RTK.
- [x] Auto-Link Semântico (Soft-Links).

### Fase Atual: Inteligência Superior (Fase 6) - CONCLUÍDO
- [x] **Real-time Watcher:** Sincronização instantânea do Obsidian para o SQLite (fim do gap de 6h).

### Entrega 13 — 09/06/2026 (Ciclo de Sonho Completo & OAuth)
**Resumo da entrega:** Fase 7 concluída. O Hive-Mind agora consolida memórias e sincroniza com o Vault.
**O que foi implementado:**
- **Reflexão Episódica:** Motor que extrai fatos e preferências de observações brutas.
- **Sincronização com o Vault:** Escrita automática de memórias consolidadas em `brain/Consolidated.md`.
- **OAuth Inquebrável:** Fluxo Loopback para Google e Codex-Handshake para OpenAI, permitindo login via terminal.
- **Auto-Discovery de Elite:** Descoberta dinâmica de modelos (incluindo Codex 5.x) em tempo real.
- **UX Maestro:** Interface `setup-dreamer.sh` unificada para todos os provedores.
**Vantagem:** O Ciclo de Sonho agora funciona de ponta a ponta, transformando a atividade diária do agente em conhecimento persistente e legível no Obsidian.

### Fase 8 — Enxame Multi-Máquina (P2P Sync) - CONCLUÍDO
- [x] Migração de IDs para UUID v4 (prevenção de colisões P2P).
- [x] Implementação de Determinismo de Hash no Ciclo de Sonho.
- [x] Swarm Auditor para verificação de integridade entre Vault e SQLite.
- [x] Suporte a sincronização descentralizada via Syncthing.

---

### Próximas Fases
- [x] Fase 9 — Fusão Semântica e Consenso (Semantic Merge). — CONCLUÍDO
- [x] Fase 10 — Memória Visual Avançada (Deep Portal) — EM FINALIZAÇÃO (multimodal docs)

### Fase 2 — Refatoração do Indexador (Graphify 2.0) - OK
### Fase 3 — Unificação Temporal e Motor Híbrido - OK
### Fase 4 — Obsidian como Interface (Portal) - OK
### Fase 6 — Real-time Watcher - OK
### Fase 7 — O Ciclo de Sonho (Hive-Dreamer) - OK

---

## 8. Política de atualização do documento

### Entrega 12 — 10/06/2026 (Início do Hive-Dreamer)
**Resumo da entrega:** Fase 7 iniciada com motor maestro multi-provider.
**O que foi implementado:**
- Criado o motor `scripts/dream_cycle.py`.
- Suporte agnóstico a LLMs: Gemini (Cloud), DeepSeek (Cloud) e Ollama (Local).
- Implementado Estágio 1: Reflexão Episódica (Extração de fatos e preferências).
- Sistema de controle de consolidação via metadados no SQLite.
**Próximos passos:** Implementar escrita automática de fatos no Vault (Estágio 2).

### Entrega 11 — 09/06/2026 (Real-time Watcher)
**Resumo da entrega:** Fase 6 concluída. O Hive-Mind agora é "Cérebro Acordado".
**O que foi implementado:**
- Modificado `graphify/graphify/watch.py` para incluir arquivos `.md` no ciclo de rebuild automático.
- Corrigida lógica de exportação UMC para rodar mesmo quando não há mudança na topologia (garantindo atualização de conteúdo/vetores).
- Criado script de serviço `scripts/start-watcher.sh`.
- Instalada dependência `watchdog` no ambiente virtual.
**Vantagem:** O gap de 6 horas foi eliminado. Qualquer alteração no Obsidian é refletida no SQLite e nos vetores em ~2 segundos.

### Entrega 10 — 09/06/2026 (Criptografia de Segredos & Vault)
**Resumo da entrega:** Implementação do Hive-Mind Vault com criptografia de nível de campo.

---

## 11. Definição geral de pronto
O Hive-Mind está agora em estado de **Sincronização Ativa**. O "sistema nervoso" (SQLite) reage instantaneamente aos estímulos do "corpo" (Obsidian).

---

## Relatório de Entrega — Sprints A→D (Fases HM-11 e HM-12)

**Data:** 2026-06-13
**Testes:** 191 passando, 0 skipped, 0 falhas
**Commits:** 06f78a1 (Sprint A+B) · e1a1a51 (Sprint C) · 0b3d632 (Sprint D)

| Módulo | Propósito | Interface pública | Config/Deps | Sprint |
|--------|-----------|-------------------|-------------|--------|
| `core/memory/` (package) | Extrai toda a lógica pura de memória do monólito `sinapse-memory.py` para submodules testáveis sem globals de módulo | `query_vault_knowledge`, `save_decision`, `save_learning`, `pre_prompt_build`, `post_session_end`, `health_check`, backends: `umc`, `neural_memory`, `graphify`, `filesystem`, `http` | Sem deps externas novas; compatibilidade monkeypatch preservada | A1 |
| `core/database._reciprocal_rank_fusion` | Combina ranking FTS5 e vetorial em score único via RRF (Cormack 2009, k=60) | `_reciprocal_rank_fusion(ranked_lists, k=60) -> list[str]` (usada internamente por `query_hybrid`) | Pure Python / `collections.defaultdict` | A3 |
| `scripts/syncthing_watcher.py` | Monitora eventos P2P do Syncthing e dispara `audit_memory.py --fix` ao detectar conflito `.sync-conflict-*` | `poll_once(last_event_id) -> int`, `run_loop()` | `SYNCTHING_API_KEY` + `SYNCTHING_URL` em `.env`; `requests`; falha-segura se Syncthing offline | B2 |
| `scripts/hive_analytics.py` | Camada analítica read-only sobre `hive_mind.db` via DuckDB; nunca bloqueia WAL dos escritores SQLite | `run(query_name, db_path=None) -> DataFrame\|list` — queries: `growth`, `top_topics`, `quarantine_rate`, `intent_by_goal` | `duckdb` (obrigatório); `pandas` (opcional) | B3 |
| `core/hnsw_index.py` | Índice vetorial HNSW incremental via hnswlib; persiste em `hnsw_neurons.idx`; degrada graciosamente se hnswlib ausente | `load_or_create(dim)`, `add_neuron(id, vector, conn)`, `search(vector, k) -> list[dict]`, `rebuild_from_db(conn, embed_fn)`, `incremental_update(conn, embed_fn)` | `hnswlib` (opcional); `HNSW_DIM` env (default 384); rastreia `indexed_at` na tabela `neurons` | B4 |
| `scripts/planner.py` + MCP `sinapse_plan_goal` | Decompõe objetivos em passos atômicos via LLM e persiste na tabela `goals` (Intent Memory) | `decompose_goal(goal, context) -> list[dict]`, `save_goal(goal, steps, conn) -> goal_id`; MCP: `sinapse_plan_goal(goal, context?)` | `pydantic`; delega geração ao `dream_cycle.call_llm_with_fallback`; tabela `goals` criada idempotentemente | C1 |
| `causal_edges` + `get_causal_neighbors` | Grafo causal entre neurônios (C→E com label e confidence); BFS multi-hop para recuperação de contexto causal | `get_causal_neighbors(conn, neuron_id, hops=2) -> list[dict]`; migração idempotente via `ensure_migrations` | Pure SQLite; índices em `cause_neuron_id` e `effect_neuron_id` | C3 |
| `core/signing.py` | Assina neurônios para exportação federada com Ed25519; fingerprint SHA-256 do pubkey; payload canônico exclui campos voláteis | `generate_keypair(name)`, `sign_neuron(neuron, key_name) -> dict`, `verify_neuron(neuron, pubkey) -> bool` | `cryptography`; chaves PEM em `config/keys/` (gitignored, chmod 0o600) | D2 |
| `core/redactor.py` | Redação irreversível de PII/segredos de neurônios antes de exportação federada; nunca muta dados locais | `redact_for_export(text) -> str`, `redact_neuron(neuron) -> dict` | Pure Python / `re`; cobre: tokens API, e-mail, IPv4/v6, paths, chaves SSH, CPF/CNPJ, telefones | D3 |
| `POST /api/v1/neurons/export` | Endpoint REST autenticado que exporta neurônios `shared`/`public` com redação e assinatura opcionais | Body: `{filters?, sign?, redact?}`; retorna `{neurons, count, exported_at, schema_version}`; rate-limit 10/min | Depende de `core/redactor` e `core/signing`; requer Bearer token (`SINAPSE_API_KEY`) | D1 |
