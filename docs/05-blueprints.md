# 05 — Blueprints e Fluxogramas

> **Hive-Mind v2.0.0** — Diagramas de arquitetura e fluxos em ASCII (compatível com qualquer editor Markdown).

---

## 1. Arquitetura de 4 Camadas

```
  ┌───────────────────────────────────────────────────────────────────┐
  │                        AGENTES DE IA                              │
  │                                                                   │
  │   ┌──────────┐  ┌────────────┐  ┌───────────┐  ┌─────────────┐  │
  │   │  Hermes  │  │ Claude Code│  │ Codex CLI  │  │ Outros MCP  │  │
  │   │  Agent   │  │ (hooks +   │  │ (hooks +   │  │ (Cursor,    │  │
  │   │ (plugin) │  │  MCP)      │  │  MCP)      │  │  OpenClaw)  │  │
  │   └────┬─────┘  └─────┬──────┘  └─────┬─────┘  └──────┬──────┘  │
  └────────┼──────────────┼───────────────┼───────────────┼──────────┘
           │              │               │               │
  ┌────────▼──────────────▼───────────────▼───────────────▼──────────┐
  │                    CAMADA DE INTEGRAÇÃO                           │
  │                                                                   │
  │  sinapse-memory.py   sinapse-mcp.py   sinapse-hook.py            │
  │  (Plugin nativo)     (MCP stdio)      (Hook universal)           │
  │                              │                                    │
  │                       sinapse-api.py                              │
  │                       (REST :37702)                               │
  │                       sinapse-write.py                            │
  │                       (CLI standalone)                            │
  └──────────────────────────────┬────────────────────────────────────┘
                                 │
  ┌──────────────────────────────▼────────────────────────────────────┐
  │                    BACKENDS DE MEMÓRIA                            │
  │                                                                   │
  │  ┌───────────────┐  ┌─────────────┐  ┌──────────┐  ┌─────────┐  │
  │  │ UMC (SQLite)  │  │  claude-mem │  │  Neural  │  │   RTK   │  │
  │  │ FTS5 + vec    │  │  :37700     │  │  Memory  │  │  (Rust) │  │
  │  │ neurons +     │  │  temporal   │  │ spreading│  │  shell  │  │
  │  │ synapses      │  │  tracking   │  │activation│  │  optim. │  │
  │  └───────┬───────┘  └──────┬──────┘  └────┬─────┘  └─────────┘  │
  └──────────┼─────────────────┼──────────────┼──────────────────────┘
             │                 │              │
  ┌──────────▼─────────────────▼──────────────▼──────────────────────┐
  │                         STORAGE                                   │
  │                                                                   │
  │   hive_mind.db          cerebro/              backups/            │
  │   (UMC — SQLite +       (Vault Obsidian)      (daily cp)          │
  │    sqlite-vec)          atlas/ brain/                             │
  │                         work/active/                              │
  └───────────────────────────────────────────────────────────────────┘
```

---

## 2. Fluxo de Leitura (Read Path)

```
  Usuário escreve mensagem para o agente
                │
                ▼
  Hook SessionStart / pre_gateway_dispatch
                │
                ▼
  _query_vault_knowledge(query, timeout=8s)
                │
        ┌───────┴────────────────────────────────────┐
        │               (paralelo)                   │
        ▼               ▼              ▼             ▼
  ┌──────────┐   ┌──────────┐   ┌──────────┐  ┌──────────┐
  │ UMC SQL  │   │claude-mem│   │NeuralMem │  │Filesystem│
  │ FTS5     │   │ HTTP     │   │spreading │  │scan *.md │
  │ KNN vec  │   │ :37700   │   │activation│  │TTL 30s   │
  │          │   │ timeout3s│   │timeout 5s│  │          │
  └────┬─────┘   └────┬─────┘   └────┬─────┘  └────┬─────┘
       │              │              │              │
       └──────────────┴──────────────┴──────────────┘
                             │
                     merge + dedup
                    (source_file + title)
                             │
                     format(top-5, max 3000 chars)
                             │
                             ▼
              inject no system_message do agente
                             │
                             ▼
  Agente responde com contexto do vault
```

---

## 3. Fluxo de Escrita (Write Path)

```
  Agente chama tool de memória
  (sinapse_save_decision | sinapse_save_learning | memory_add)
                │
                ▼
  Hook PostToolUse detecta DECISION_TOOLS
                │
                ├── _sanitize_slug(title)
                │     "Minha Decisão" → "2026-06-10-minha-decisao"
                │
                ├── _validate_frontmatter_yaml()
                │     checa: tags, status, created
                │
                ├── secret_scan(content)
                │     regex: sk-proj-*, AKIA*, Bearer, api_key=
                │     → Fernet encrypt → vault table
                │     → replace by "[SECRET:uuid]" no conteúdo
                │
                ├── _atomic_write(path, content)
                │     mkstemp() → write → os.replace()  ← atômico
                │
                └── Se LEARNING_SIGNALS no content:
                      _save_learning() → brain/Patterns.md
                      _dedup_check() → não duplica mesmo título
                                │
                                ▼ (~2 segundos)
              Watcher detecta FileModifiedEvent
                                │
                                ▼
              Graphify reindexa arquivo:
              UPDATE neurons / synapses / FTS5 / vec

  ─ ─ ─ ─ ─ ─ ─ Fim de sessão ─ ─ ─ ─ ─ ─ ─

  Hook Stop / on_session_end
                │
                ├── _update_current_state()
                │     brain/Current State.md
                │     (WikiLinks para decisões da sessão)
                │
                └── INSERT observations(type='session_end')
```

---

## 4. Dream Cycle — Pipeline de Consolidação

```
  hive_mind.db
  observations (archived=0, não processadas)
         │
         ▼  (batch de até N por execução)
  ┌──────────────────────┐
  │     DISTILLER        │
  │  LLM → DistilledFact │
  │  JSON schema via      │
  │  Pydantic            │
  └──────────┬───────────┘
             │ DistilledFact
             ▼
  ┌──────────────────────┐         ┌──────────────────────┐
  │     VALIDATOR        │──repro→ │     QUARENTENA       │
  │  LLM: aprovado?      │ vado    │  archived=2           │
  │  max 2 retries        │         │  (não perdido)        │
  └──────────┬───────────┘         └──────────────────────┘
             │ aprovado
             ▼
  ┌──────────────────────┐
  │      ROUTER          │
  │  classifica destino  │
  │  check duplicata     │
  │  cosine > 0.92       │
  └──────────┬───────────┘
             │
     ┌───────┴────────┐
     │                │
     ▼ novo           ▼ duplicata
  ┌─────────────┐  ┌───────────────┐
  │ ATLAS WRITE │  │ MERGE         │
  │ atomic write│  │ append unique │
  │ INSERT neuron│  │ insights only │
  └──────┬──────┘  └───────┬───────┘
         │                 │
         └────────┬─────────┘
                  │
                  ▼
  UPDATE observations SET archived=1
  (consolidated_at = NOW())
```

---

## 5. Circuit Breaker (Fallback Chain)

```
  Query chega no motor de busca
         │
         ▼
  ┌──────────────────┐      3+ falhas    ┌───────────────┐
  │ UMC SQL (FTS5 +  │──────────────────▶│   COOLDOWN    │
  │  KNN vec)        │   cooldown 30s    │   30 segundos │
  └──────┬───────────┘                   └───────────────┘
         │ ok
         ▼
  ┌──────────────────┐      3+ falhas    ┌───────────────┐
  │ claude-mem       │──────────────────▶│   COOLDOWN    │
  │ HTTP :37700      │   cooldown 30s    │   30 segundos │
  └──────┬───────────┘                   └───────────────┘
         │ ok
         ▼
  ┌──────────────────┐      3+ falhas    ┌───────────────┐
  │ NeuralMemory     │──────────────────▶│   COOLDOWN    │
  │ spreading activ. │   cooldown 30s    │   30 segundos │
  └──────┬───────────┘                   └───────────────┘
         │ ok
         ▼
  ┌──────────────────┐      3+ falhas    ┌───────────────┐
  │ Filesystem scan  │──────────────────▶│   None        │
  │ cerebro/*.md     │                   │ (sem contexto)│
  └──────┬───────────┘                   └───────────────┘
         │ ok
         ▼
  resultado retornado ao agente

  Nota: resultados vazios (não encontrado) NÃO contam como falha.
        Apenas exceções Python e timeouts disparam o circuit breaker.
```

---

## 6. Pipeline Graphify (Indexação Estrutural)

```
  cerebro/*.md  (vault Obsidian)
         │
         ▼
  ┌──────────────┐
  │  PARSER      │
  │  frontmatter │  extrai: title, tags, WikiLinks
  │  YAML        │
  └──────┬───────┘
         │
         ▼
  ┌───────────────────────────────────────────┐
  │  BACKEND (escolhido por disponibilidade)  │
  │                                           │
  │  1º: Gemini 2.5 Flash (cloud)             │
  │      NER: entidades + relações            │
  │                                           │
  │  2º: Ollama Qwen 2.5 Coder 3B (local)    │
  │      NER local, sem API key               │
  │                                           │
  │  3º: tree-sitter + regex (determinístico) │
  │      parsing sintático, sempre funciona   │
  └──────┬────────────────────────────────────┘
         │ entities + relations
         ▼
  ┌──────────────────┐
  │  EMBEDDING       │
  │  all-MiniLM-L6   │  384 dimensões, local
  │  -v2 (fastembed) │
  └──────┬───────────┘
         │ vetor 384d
         ▼
  ┌────────────────────────────────────────────┐
  │  hive_mind.db                              │
  │  INSERT/UPDATE neurons (id, title, hash)   │
  │  INSERT/UPDATE synapses (source, target)   │
  │  UPDATE search_fts (trigger automático)    │
  │  UPDATE search_vec (vec0 HNSW)             │
  └────────────────────────────────────────────┘
```

---

## 7. Integração Multi-Agente

```
  ┌────────────────────────────────────────────────────────────────┐
  │  HERMES (Plugin Nativo)                                        │
  │   pre_gateway_dispatch → post_tool_call → on_session_end       │
  │   Arquivo: plugins/hermes/sinapse-memory.py                    │
  └────────────────────────────────┬───────────────────────────────┘
                                   │
  ┌────────────────────────────────┼───────────────────────────────┐
  │  CLAUDE CODE (MCP + Hooks)     │                               │
  │   SessionStart ────────────────┤                               │
  │   PostToolUse  ────────────────┤──▶  sinapse-hook.py           │
  │   Stop         ────────────────┤                               │
  │   MCP tools ──────────────────▶│──▶  sinapse-mcp.py (9 tools) │
  └────────────────────────────────┤───────────────────────────────┘
                                   │
  ┌────────────────────────────────┼───────────────────────────────┐
  │  CODEX CLI (MCP + Hooks)       │                               │
  │   SessionStart ────────────────┤                               │
  │   PostToolUse  ────────────────┤──▶  sinapse-hook.py           │
  │   Stop         ────────────────┤                               │
  │   MCP tools ──────────────────▶│──▶  sinapse-mcp.py (9 tools) │
  └────────────────────────────────┤───────────────────────────────┘
                                   │
  ┌────────────────────────────────┼───────────────────────────────┐
  │  OUTROS (MCP only)             │                               │
  │  Cursor, OpenClaw, KiloCode ───┤──▶  sinapse-mcp.py (9 tools) │
  └────────────────────────────────┤───────────────────────────────┘
                                   │
  ┌────────────────────────────────▼───────────────────────────────┐
  │  REST API (cloud mode)                                         │
  │  sinapse-api.py :37702 (Bearer token)                          │
  │  /api/v1/query  /api/v1/observations  /api/v1/health           │
  └────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
                          hive_mind.db (UMC)
```

---

## 8. Atomic Write

```
  _atomic_write(filepath, content)
         │
         ▼
  mkstemp(dir=parent_dir)
         │ retorna (fd, tmppath)
         ▼
  write(fd, content.encode('utf-8'))
         │
         ▼
  close(fd)
         │
         ▼
  os.replace(tmppath, filepath)
         │                         ← ATÔMICO no Linux/POSIX
         ▼                           rename(2) syscall
  arquivo final íntegro

  Cenários de falha:
    Processo morre antes do replace:
      tmppath fica como orphan (não afeta filepath)
    Processo morre durante o replace:
      Kernel garante atomicidade — filepath ou velho ou novo
    Disco cheio durante write:
      write() lança OSError — tmppath descartado, filepath intacto
```

---

## 9. P2P Sync (Sincronização Multi-Máquina)

```
  Máquina A                    Syncthing                    Máquina B
  (cerebro/)                   (transport)                  (cerebro/)
     │                              │                            │
     │ arquivo.md criado/editado    │                            │
     │──────────────────────────────▶                            │
     │                              │──────────────────────────▶│
     │                              │  arquivo.md recebido      │
     │                                                           │
     │                                    Watcher detecta (~2s) │
     │                                    OU cron audit_memory.py│
     │                                                           │
     │                                    audit_memory.py --fix  │
     │                                       │                   │
     │                                       ▼                   │
     │                                    SHA-256(arquivo.md)    │
     │                                       │                   │
     │                                 hash == neurons.hash?     │
     │                                    │         │            │
     │                               sim (ok)   não (divergência)│
     │                                    │         │            │
     │                                  skip    reindex neuron   │
     │                                           + INSERT        │
     │                                          ambiguities      │
     │                                               │           │
     │                                        Dream Cycle:       │
     │                                        Síntese Dialética  │
     │                                        (merge/choose/     │
     │                                         branch)           │
```

---

## 10. Deploy VPS

```
  Internet
     │ HTTPS (TLS via nginx/Caddy)
     ▼
  ┌──────────────────────────────────────────────────────────┐
  │  VPS                                                     │
  │                                                          │
  │  nginx/Caddy (:443) → proxy → sinapse-api.py (:37702)  │
  │                                                          │
  │  systemd units:                                          │
  │    hive-mind-api.service      (sinapse-api.py)           │
  │    hive-mind-watcher.service  (start-watcher.sh)         │
  │    claude-mem.service         (bun run serve :37700)     │
  │    syncthing.service          (P2P sync)                 │
  │    ollama.service             (:11434)                   │
  │                                                          │
  │  cron:                                                   │
  │    0 * * * * audit_memory.py --fix                       │
  │    0 3 * * * backup hive_mind.db                         │
  │                                                          │
  │  hive_mind.db ← Watcher ← cerebro/ ← Syncthing ──────┐ │
  │                                                       │ │
  └───────────────────────────────────────────────────────┼─┘
                                                          │
                                                   ┌──────┴──────┐
                                                   │  Outras      │
                                                   │  máquinas    │
                                                   │  (Syncthing) │
                                                   └─────────────┘
```
