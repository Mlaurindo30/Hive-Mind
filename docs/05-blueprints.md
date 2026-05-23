# 05 — Blueprints e Fluxogramas

> **Sinapse Agent v1.1.0** — Diagramas Mermaid da arquitetura e fluxos de dados.
> Renderize em: https://mermaid.live ou GitHub (nativo).

---

## 1. Arquitetura de 4 Camadas

```mermaid
graph TB
    subgraph AGENTS["🤖 Agentes de IA"]
        H[Hermes Agent<br/>Plugin Nativo]
        CC[Claude Code<br/>MCP + Hooks]
        CX[Codex CLI<br/>MCP + Hooks]
        KC[Kilo Code<br/>MCP]
        OC[OpenClaw<br/>MCP]
    end

    subgraph INTEGRATION["🔌 Camada de Integração"]
        PLUGIN[sinapse-memory.py<br/>Plugin Python<br/>Hooks: pre_prompt, post_tool, post_session]
        MCP[sinapse-mcp.py<br/>MCP Server stdio<br/>5 tools]
        CLI[sinapse-write.py<br/>CLI Standalone<br/>5 subcommands]
        HOOK[sinapse-hook.py<br/>Hook Script<br/>SessionStart, Stop, PostToolUse]
    end

    subgraph BACKENDS["🧠 Backends de Memória"]
        NM[NeuralMemory<br/>Spreading Activation<br/>24 tipos de relações]
        CM[claude-mem<br/>FTS5 + Chroma<br/>HTTP :37700]
        GF[Graphify<br/>Leiden Clustering<br/>graph.json]
        RTK[RTK<br/>Shell Optimization<br/>Rust binary]
    end

    subgraph STORAGE["💾 Storage"]
        VAULT[Vault Obsidian<br/>cerebro/<br/>~200 .md files]
        GRAPH[graph.json<br/>1266+ nodes<br/>1319+ edges]
        SQLITE[(SQLite FTS5<br/>claude-mem.db)]
        CHROMA[(ChromaDB<br/>embeddings)]
    end

    H --> PLUGIN
    CC --> MCP
    CC --> HOOK
    CX --> MCP
    CX --> HOOK
    KC --> MCP
    OC --> MCP
    
    PLUGIN --> NM
    PLUGIN --> CM
    PLUGIN --> GF
    MCP --> NM
    MCP --> CM
    MCP --> GF
    CLI --> NM
    CLI --> CM
    CLI --> GF
    
    NM --> VAULT
    CM --> SQLITE
    CM --> CHROMA
    GF --> GRAPH
    GRAPH --> VAULT
```

---

## 2. Fluxo de Leitura (Read Path)

```mermaid
sequenceDiagram
    actor User as 👤 Usuário
    participant Agent as 🤖 Agente
    participant Hook as 🔌 Hook
    participant Engine as ⚙️ Query Engine
    participant NM as 🧠 NeuralMemory
    participant CM as 📊 claude-mem
    participant GF as 🗂️ Graphify
    participant Vault as 💾 Vault

    User->>Agent: Pergunta sobre projeto
    Agent->>Hook: pre_prompt_build / SessionStart
    
    Hook->>Engine: _query_vault_knowledge(query)
    
    Engine->>NM: nmem recall (spreading activation)
    alt NM encontra resultados
        NM-->>Engine: memories com confidence
    else NM falha/timeout
        Engine->>CM: HTTP /api/context/semantic
        alt CM encontra (Chroma)
            CM-->>Engine: contexto semântico
        else CM falha (FTS5 fallback)
            Engine->>GF: busca textual em graph.json
            alt GF encontra
                GF-->>Engine: nodes + edges
            else tudo falha
                Engine-->>Hook: None (sem contexto)
            end
        end
    end
    
    Engine-->>Hook: contexto formatado
    Hook-->>Agent: system_message + contexto
    Agent-->>User: Resposta com contexto do vault
```

---

## 3. Fluxo de Escrita (Write Path)

```mermaid
sequenceDiagram
    actor User as 👤 Usuário
    participant Agent as 🤖 Agente
    participant Hook as 🔌 Hook
    participant Writer as ✍️ Write Engine
    participant Vault as 💾 Vault
    participant Cron as ⏰ Cron (6h)
    participant Graph as 🗂️ graph.json

    User->>Agent: "Decidi migrar o servidor"
    Agent->>Agent: tool: memory_add(title, content)
    
    Agent->>Hook: post_tool_use / PostToolUse
    
    Hook->>Writer: detecta DECISION_TOOLS
    Writer->>Writer: _sanitize_slug(title)
    Writer->>Writer: _atomic_write(filepath, note)
    Writer->>Vault: work/active/2026-05-23-migrar-servidor.md
    
    alt conteúdo contém LEARNING_SIGNALS
        Writer->>Writer: _save_learning(title, content)
        Writer->>Writer: verifica deduplicação
        Writer->>Vault: append brain/Patterns.md
    end
    
    Note over Agent,Vault: ... sessão continua ...
    
    Agent->>Hook: post_session_end / Stop hook
    Hook->>Writer: _update_current_state(decisions, learnings, summary)
    Writer->>Vault: atualiza brain/Current State.md
    
    Note over Vault,Graph: 0-6 horas depois...
    
    Cron->>Graph: build-graph.sh
    Graph->>Vault: graphify update cerebro/
    Graph->>Graph: backup graph.json.bak
    Graph->>Graph: valida JSON
```

---

## 4. Circuit Breaker + Fallback Chain

```mermaid
graph TD
    Q[Query: "projeto thoth"] --> B0{NeuralMemory<br/>disponível?}
    
    B0 -->|✅ Sim| NM[nmem recall]
    B0 -->|❌ 3+ falhas| B1{claude-mem<br/>disponível?}
    NM -->|Resultado| FIM[✅ Retorna contexto]
    NM -->|Falha| B1
    
    B1 -->|✅ Sim| CM[HTTP /api/context/semantic]
    B1 -->|❌ 3+ falhas| B2{Graphify<br/>disponível?}
    CM -->|Resultado| FIM
    CM -->|Falha| B1F{FTS5 fallback}
    B1F -->|Resultado| FIM
    B1F -->|Falha| B2
    
    B2 -->|✅ Sim| GF[graph.json textual search]
    B2 -->|❌ 3+ falhas| NULL[❌ None]
    GF -->|Resultado| FIM
    GF -->|Falha| NULL
```

---

## 5. Pipeline de Indexação (Graphify)

```mermaid
graph LR
    MD[Arquivos .md<br/>no vault] --> PARSE{Backend?}
    
    PARSE -->|Gemini| GEM[Gemini 2.5 Flash<br/>NER + relações]
    PARSE -->|Ollama| OLL[Qwen 2.5 Coder 3B<br/>NER local]
    PARSE -->|AST-only| TS[tree-sitter + regex<br/>parsing sintático]
    
    GEM --> ENT[Entidades + Relações]
    OLL --> ENT
    TS --> ENT
    
    ENT --> EMB{BGE-M3?}
    EMB -->|Sim| VEC[Embeddings 1024-d]
    EMB -->|Não| SKIP[Skip embeddings]
    
    VEC --> LEIDEN[Leiden Clustering<br/>agrupa em comunidades]
    SKIP --> LEIDEN
    
    LEIDEN --> JSON[graph.json<br/>nodes + edges + communities]
    
    JSON --> VAL{JSON válido?}
    VAL -->|Sim| SAVE[Salva + backup .bak]
    VAL -->|Não| RESTORE[Restaura backup]
```

---

## 6. Integração Multi-Agente

```mermaid
graph TB
    subgraph HERMES["Hermes Agent (Plugin Nativo)"]
        H1[pre_prompt_build] --> H2[post_tool_use]
        H2 --> H3[post_session_end]
    end
    
    subgraph CLAUDE["Claude Code (MCP + Hooks)"]
        C1[SessionStart<br/>sinapse-hook.py] --> C2[PostToolUse<br/>sinapse-hook.py]
        C2 --> C3[Stop<br/>sinapse-hook.py]
        C4[MCP Tools<br/>sinapse-mcp.py] 
    end
    
    subgraph CODEX["Codex CLI (MCP + Hooks)"]
        X1[SessionStart<br/>sinapse-hook.py] --> X2[PostToolUse<br/>sinapse-hook.py]
        X2 --> X3[Stop<br/>sinapse-hook.py]
        X4[MCP Tools<br/>sinapse-mcp.py]
    end
    
    subgraph OTHER["Outros Agentes (MCP)"]
        O1[Kilo Code] --> O1M[MCP Tools]
        O2[OpenClaw] --> O2M[MCP Tools]
        O3[Copilot] --> O3M[MCP Tools]
    end
    
    subgraph CORE["Sinapse Core"]
        SM[sinapse-memory.py<br/>984 linhas]
    end
    
    H1 --> SM
    H2 --> SM
    H3 --> SM
    C1 --> SM
    C2 --> SM
    C3 --> SM
    C4 --> SM
    X1 --> SM
    X2 --> SM
    X3 --> SM
    X4 --> SM
    O1M --> SM
    O2M --> SM
    O3M --> SM
```

---

## 7. Atomic Write Guarantee

```mermaid
sequenceDiagram
    participant Writer as ✍️ _atomic_write()
    participant Temp as /tmp/file.tmp
    participant Final as cerebro/work/active/file.md
    participant FS as Filesystem

    Writer->>Temp: mkstemp() → fd
    Writer->>Temp: write(content)
    Writer->>Temp: close()
    Writer->>FS: os.replace(tmp, final)
    
    Note over Writer,FS: os.replace() é atômico no Linux
    Note over Writer,FS: Se processo morrer antes: tmp é orphan
    Note over Writer,FS: Se processo morrer depois: arquivo está íntegro
```

---

## 8. Deploy Architecture

```mermaid
graph TB
    subgraph VPS["VPS / Servidor Local"]
        OLLAMA[Ollama<br/>:11434]
        WORKER[claude-mem Worker<br/>systemd service<br/>:37700]
        CRON[Cron Jobs<br/>build-graph.sh 6h<br/>sync-diario.sh dom]
        VAULT2[Vault cerebro/<br/>Git repo]
    end
    
    subgraph AGENTS2["Agentes Conectados"]
        HERMES2[Hermes<br/>Plugin Python]
        CLAUDE2[Claude Code<br/>MCP + Hooks]
        CODEX2[Codex CLI<br/>MCP + Hooks]
    end
    
    HERMES2 -->|hooks| VAULT2
    CLAUDE2 -->|MCP + hooks| VAULT2
    CODEX2 -->|MCP + hooks| VAULT2
    
    VAULT2 -->|indexa| CRON
    CRON -->|graph.json| VAULT2
    WORKER -->|HTTP API| VAULT2
    OLLAMA -->|LLM| VAULT2
```
