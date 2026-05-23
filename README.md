# Sinapse Agent

Camada de memória universal para agentes de IA. Indexa um vault Obsidian em um knowledge graph queryable via Graphify, complementado por tracking granular de eventos (claude-mem) e otimização de execução (RTK). **Um clone, um `./install.sh`, todos os agentes conectados.**

---

## Filosofia

Agentes de IA sofrem de amnésia entre sessões. O Sinapse Agent resolve isso com uma arquitetura de três camadas sobre um vault Obsidian como fonte única de verdade. O vault é indexado em um knowledge graph que qualquer agente pode consultar via MCP. Decisões e aprendizados são escritos de volta ao vault, fechando o ciclo de memória persistente.

---

## Arquitetura (3 Camadas)

```
┌─────────────────────────────────────────────────────────────────────┐
│                        SINAPSE AGENT                                │
│              Camada de Memória Universal para Agentes               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │                    VAULT OBSIDIAN                           │   │
│   │                    cerebro/                                 │   │
│   │              ★ Fonte única de verdade ★                     │   │
│   │                                                             │   │
│   │  brain/  atoms/  work/  org/  reference/  templates/       │   │
│   │  bases/  thinking/  AGENTS.md  CLAUDE.md  GEMINI.md        │   │
│   └───────┬────────────────────────────┬───────────────────────┘   │
│           │                            │                           │
│           ▼                            ▲                           │
│   ┌───────────────┐          ┌───────────────────┐                 │
│   │   LEITURA     │          │     ESCRITA       │                 │
│   │ (query graph) │          │ (plugin hermes +  │                 │
│   │               │          │  claude-mem sync) │                 │
│   └───────┬───────┘          └────────┬──────────┘                 │
│           │                           │                            │
│           ▼                           │                            │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │                                                             │   │
│   │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │   │
│   │  │  CAMADA 1    │  │  CAMADA 2    │  │  CAMADA 3    │       │   │
│   │  │  Estrutural  │  │  Temporal    │  │  Execução    │       │   │
│   │  │              │  │              │  │              │       │   │
│   │  │  Graphify    │  │  claude-mem  │  │  RTK         │       │   │
│   │  │              │  │              │  │              │       │   │
│   │  │  O QUE?      │  │  QUEM/QUAND? │  │  COMO?       │       │   │
│   │  │  Como se     │  │  Contexto    │  │  Otimizar    │       │   │
│   │  │  conecta?    │  │  Histórico   │  │  comandos    │       │   │
│   │  │              │  │              │  │              │       │   │
│   │  │  graph.json  │  │  SQLite      │  │  pre_tool    │       │   │
│   │  │  491 nodes   │  │  + Chroma    │  │  _call hook  │       │   │
│   │  │  606 edges   │  │  + FTS5      │  │              │       │   │
│   │  │  55 comunid. │  │              │  │              │       │   │
│   │  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘       │   │
│   │         │                 │                 │               │   │
│   │         ▼                 ▼                 ▼               │   │
│   │  ┌─────────────────────────────────────────────────────┐     │   │
│   │  │                  MCP SERVERS                        │     │   │
│   │  │           graphify.json + claude-mem.json           │     │   │
│   │  └──────────────────────┬──────────────────────────────┘     │   │
│   │                         │                                    │   │
│   └─────────────────────────┼────────────────────────────────────┘   │
│                             │                                        │
│                             ▼                                        │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │                    AGENTES                                  │   │
│   │                                                             │   │
│   │  ┌────────┐ ┌───────────┐ ┌────────┐ ┌──────┐ ┌────────┐   │   │
│   │  │ Thoth  │ │Claude Code│ │ Codex  │ │Cursor│ │OpenCode│   │   │
│   │  │(Hermes)│ └───────────┘ └────────┘ └──────┘ └────────┘   │   │
│   │  └────────┘ ┌───────────┐ ┌──────────┐ ┌───────────┐       │   │
│   │             │Gemini CLI │ │ Copilot  │ │ OpenClaw  │       │   │
│   │             └───────────┘ └──────────┘ └───────────┘       │   │
│   └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

| Camada | Ferramenta | Pergunta que responde | Dados |
|--------|-----------|----------------------|-------|
| 1 — Estrutural | **Graphify** | Como os conceitos se conectam? | `graph.json` (491 nodes, 606 edges, 55 communities) |
| 2 — Temporal | **claude-mem** | Quem fez o quê? Quando? | SQLite + Chroma (FTS5 search) |
| 3 — Execução | **RTK** | Como otimizar esse comando? | Hook `pre_tool_call` no Hermes |
| 4 — Associativa | **NeuralMemory** | Como os conceitos se relacionam? | Spreading activation (nmem recall) |

---

## Vault: Estrutura Final

```
cerebro/
├── brain/          ← Conhecimento operacional (North Star, Patterns, Gotchas, Key Decisions)
├── atoms/          ← Notas Zettelkasten (1 ideia = 1 node, densamente linkadas)
├── work/           ← Projetos (active/, archive/, meetings/, pipeline/)
├── org/            ← Pessoas e times (people/, teams/)
├── reference/      ← Documentação atemporal (business docs, tech specs)
├── templates/      ← Atom Note, Work Note, Decision Record, Thinking Note
├── bases/          ← 7 database views (Work Dashboard, People Directory, etc.)
├── thinking/       ← Scratchpad temporário
├── AGENTS.md       ← Cross-agent guide (Thoth, Claude Code, Codex, Gemini CLI, etc.)
├── CLAUDE.md       ← Claude Code operating manual
├── GEMINI.md       ← Gemini CLI guide
└── Home.md         ← Entry point com dashboards Obsidian
```

---

## Instalação

### Pré-requisitos

| Dependência | Obrigatório? | Nota |
|------------|-------------|------|
| Python 3.10+ | Sim | Graphify |
| uv | Automático | Fallback: pipx |
| Node.js 18+ | claude-mem | Tempo de tracking |
| Bun 1.0+ | claude-mem | Opcional (fallback: npm) |
| Ollama | Opcional | Extração semântica local |
| Obsidian | Opcional | Interface visual do vault |

### Instalação rápida

```bash
git clone <repo-url> ~/Documentos/Projects/sinapse_agent
cd ~/Documentos/Projects/sinapse_agent
./install.sh
```

O `install.sh` faz tudo (9 etapas):

1. **Verifica dependências** — Python, uv/pipx, Node, Bun, Ollama (opcional)
2. **Instala Graphify** — indexa vault (Gemini→Ollama→AST)
3. **Registra skills** — detecta e configura 12+ agentes
4. **Configura claude-mem** — compila do source, inicia worker (systemd)
5. **Instala NeuralMemory** — busca associativa com spreading activation
6. **Configura RTK** — compila Rust, instala plugin Hermes
7. **Configura MCP** — graphify + claude-mem servers
8. **Configura cron** — sync a cada 6h
9. **Plugin sinapse-memory** — multi-backend (nmem + claude-mem + graphify)

### Modelos Ollama (opcional)

```bash
ollama pull qwen2.5-coder:3b    # Extração semântica local (1.9GB)
ollama pull bge-m3               # Embeddings de alta qualidade (1.2GB)
ollama pull nomic-embed-text     # Embeddings leve (0.3GB)
```

### API Keys (opcional)

```bash
cp .env.example .env
# Configure GOOGLE_API_KEY para extração semântica com Gemini
```

---

## Configuração do Obsidian

```bash
# Flatpak
flatpak run md.obsidian.Obsidian --vault ~/Documentos/Projects/sinapse_agent/cerebro

# Snap
snap run obsidian --vault ~/Documentos/Projects/sinapse_agent/cerebro
```

Em **Configurações > Arquivos e links**, ative **Mostrar arquivos ocultos**.

---

## Solução de Problemas

| Problema | Solução |
|----------|---------|
| Graphify não instalou | `pip install -e graphify/[all]` |
| graph.json não gerado | `./scripts/build-graph.sh` |
| MCP não conecta | Verifique `~/.hermes/config.yaml` → `mcp_servers` |
| claude-mem worker parou | `systemctl --user restart sinapse-claude-mem.service` |
| RTK não otimiza | `~/.local/bin/rtk gain` |
| Plugin sinapse-memory offline | `hermes plugins enable sinapse-memory` |
| Obsidian vazio | Verifique `~/.var/app/.../obsidian.json` — vault path correto? |
| Ollama lento na extração | Use Gemini (GOOGLE_API_KEY) para primeira indexação |

---

## Licença

Apache 2.0
