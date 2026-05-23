# ARCHITECTURE.md — Sinapse Agent

Blueprint técnico da camada de memória universal para agentes de IA.

---

## Índice

1. [Visão Geral das 3 Camadas](#1-visão-geral-das-3-camadas)
2. [Fluxo de Leitura](#2-fluxo-de-leitura)
3. [Fluxo de Escrita](#3-fluxo-de-escrita)
4. [Divisão de Responsabilidades](#4-divisão-de-responsabilidades)
5. [Como Estender para Novos Agentes](#5-como-estender-para-novos-agentes)
6. [Como Adicionar Novo Projeto ao Vault](#6-como-adicionar-novo-projeto-ao-vault)
7. [Configuração do Obsidian](#7-configuração-do-obsidian)
8. [Cron e Automação](#8-cron-e-automação)
9. [Troubleshooting](#9-troubleshooting)
10. [Referência de APIs](#10-referência-de-apis)

---

## 1. Visão Geral das 3 Camadas

O Sinapse Agent organiza a memória de agentes em três camadas complementares,
cada uma respondendo a uma pergunta fundamental:

```
┌──────────────────────────────────────────────────────────────────────┐
│                                                                      │
│   CAMADA 1 — ESTRUTURAL                    Graphify                 │
│   ─────────────────────                    ────────                  │
│   Pergunta: O QUE existe no vault? Como os conceitos se conectam?    │
│                                                                      │
│   Entrada:  Arquivos .md no vault cerebro/                           │
│   Processo: Parsing → extração de entidades → embeddings →           │
│             clusterização (Leiden community detection)               │
│   Saída:    graph.json (nodes, edges, communities)                   │
│   Entrega:  MCP server (stdio/HTTP) + plugin de leitura              │
│                                                                      │
│   ═══════════════════════════════════════════════════════════════    │
│                                                                      │
│   CAMADA 2 — TEMPORAL                      claude-mem               │
│   ─────────────────────                    ──────────                │
│   Pergunta: QUEM fez o quê? QUANDO? Em qual CONTEXTO?               │
│                                                                      │
│   Entrada:  Eventos de agentes (tool uses, prompts, resultados)      │
│   Processo: Hook intercepta eventos → gera observações via LLM →     │
│             armazena em SQLite (FTS5 search)                          │
│   Saída:    Observations, corpora, timeline reports                  │
│   Entrega:  MCP server + REST API + plugin multi-agente              │
│                                                                      │
│   ═══════════════════════════════════════════════════════════════    │
│                                                                      │
│   CAMADA 3 — EXECUÇÃO                       RTK                     │
│   ─────────────────────                     ───                      │
│   Pergunta: COMO otimizar esse comando shell?                        │
│                                                                      │
│   Entrada:  Comando shell antes da execução (hook pre_tool_call)     │
│   Processo: rtk rewrite → analisa e reescreve com melhores práticas  │
│   Saída:    Comando otimizado (ou original se já estiver bom)        │
│   Entrega:  Hook no Hermes (pre_tool_call)                           │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### Fluxo de Dados entre Camadas

```
                    ┌──────────────┐
                    │   VAULT      │
                    │  cerebro/    │
                    │  (Obsidian)  │
                    └──┬───────┬──┘
                       │       │
         indexação     │       │  escrita (plugin hermes)
         (Graphify)    │       │  + sync (claude-mem)
                       │       │
              ┌────────▼──┐ ┌──▼────────┐
              │  graphify  │ │ claude-mem │
              │ graph.json │ │  SQLite    │
              │            │ │  + FTS5    │
              └─────┬──────┘ └────┬───────┘
                    │             │
                    │    MCP      │
                    ├─────────────┤
                    │             │
              ┌─────▼─────────────▼─────┐
              │      AGENTES            │
              │  Hermes, Claude, Codex  │
              │  Cursor, OpenCode, etc  │
              └─────────────────────────┘
                         │
                         │ pre_tool_call (terminal)
                         │
              ┌──────────▼──────────┐
              │        RTK          │
              │   rtk rewrite CMD   │
              │   → CMD otimizado   │
              └─────────────────────┘
```

### Mapa de Responsabilidades

```
┌───────────────┬─────────────────┬───────────────────┬─────────────────┐
│               │   CAMADA 1      │    CAMADA 2       │   CAMADA 3      │
│               │   Graphify      │    claude-mem     │   RTK           │
├───────────────┼─────────────────┼───────────────────┼─────────────────┤
│ O que          │ Arquivos .md no │ Eventos de        │ Comandos shell  │
│ processa       │ vault Obsidian  │ agentes + prompts │ antes de exec   │
├───────────────┼─────────────────┼───────────────────┼─────────────────┤
│ Como          │ tree-sitter +  │ Hook intercepta   │ Regex + regras  │
│ processa       │ regex +        │ eventos → LLM     │ determinísticas │
│               │ Leiden cluster │ gera observações  │                 │
├───────────────┼─────────────────┼───────────────────┼─────────────────┤
│ Formato de     │ graph.json     │ SQLite rows +     │ stdout string   │
│ saída          │ (JSON)         │ FTS5 search       │                 │
├───────────────┼─────────────────┼───────────────────┼─────────────────┤
│ Interface      │ MCP (stdio) +  │ MCP (stdio) +     │ Hook            │
│               │ arquivo direto  │ REST API          │ pre_tool_call   │
├───────────────┼─────────────────┼───────────────────┼─────────────────┤
│ Latência       │ < 5s (query)   │ < 500ms (search)  │ < 2s (rewrite)  │
│               │ 30-60s (build)  │ 3-10s (generate)  │                 │
├───────────────┼─────────────────┼───────────────────┼─────────────────┤
│ Dependência    │ Python 3.10+   │ Node 18+/Bun 1.0+ │ Rust binary     │
│               │ uv ou pipx      │                   │ (via pip)       │
└───────────────┴─────────────────┴───────────────────┴─────────────────┘
```

---

## 2. Fluxo de Leitura

O fluxo de leitura injeta conhecimento do vault no prompt do agente ANTES
que ele responda ao usuário. Isso garante que toda resposta tenha contexto
do que já foi pensado, decidido e aprendido.

### Diagrama de Sequência

```
Usuário         Agente           Plugin sinapse      Graphify        MCP
  │                │                    │                │              │
  │  "como era    │                    │                │              │
  │   o pricing?" │                    │                │              │
  │───────────────►                    │                │              │
  │                │                    │                │              │
  │                │ pre_prompt_build   │                │              │
  │                │───────────────────►                │              │
  │                │                    │                │              │
  │                │                    │ _query_vault   │              │
  │                │                    │ _knowledge()   │              │
  │                │                    │───────────────►              │
  │                │                    │                │              │
  │                │                    │   graph.json   │              │
  │                │                    │◄───────────────│              │
  │                │                    │                │              │
  │                │                    │ busca textual  │              │
  │                │                    │ em nodes/edges │              │
  │                │                    │ match: pricing │              │
  │                │                    │                │              │
  │                │   system_message   │                │              │
  │                │   + [Sinapse       │                │              │
  │                │    Vault Context]  │                │              │
  │                │◄───────────────────│                │              │
  │                │                    │                │              │
  │                │ (opcional: busca   │                │              │
  │                │  semântica MCP)    │                │              │
  │                │──────────────────────────────────────────────────►
  │                │                    │                │              │
  │                │◄──────────────────────────────────────────────────
  │                │                    │                │              │
  │                │ Resposta COM       │                │              │
  │                │ contexto do vault  │                │              │
  │◄───────────────│                    │                │              │
  │                │                    │                │              │
```

### Detalhamento do Plugin de Leitura

O arquivo `plugins/hermes/sinapse-memory.py` implementa três hooks:

```python
def register(ctx):
    ctx.register_hook("pre_prompt_build", _pre_prompt_build)   # leitura
    ctx.register_hook("post_tool_use", _post_tool_use)         # escrita
    ctx.register_hook("post_session_end", _post_session_end)   # fechamento
```

**pre_prompt_build** (fluxo de leitura):

```
1. Recebe user_message do hook
2. Extrai palavras-chave (split + lowercase)
3. Abre graph.json (cache local, sem rede)
4. Itera nodes: compara palavras com label + file_type
5. Itera links: compara com source + target + relation
6. Ordena matches por relevância (score de palavras)
7. Formata top 5 nodes + edges como bloco de contexto
8. Injeta no system_message antes do prompt original
9. Trunca em MAX_CONTEXT_CHARS (3000) se necessário
```

**Busca semântica avançada** (via MCP server):

Além da busca textual direta no plugin, o MCP server do Graphify expõe
ferramentas para busca semântica:

| Tool MCP | Função |
|----------|--------|
| `query_graph(query)` | Busca semântica no grafo completo (embeddings) |
| `get_node(name)` | Retorna detalhes de um nó específico |
| `get_neighbors(name)` | Lista todos os vizinhos de um nó |
| `shortest_path(a, b)` | Caminho mais curto entre dois conceitos |

### Skill de Consulta Multi-Agente

O arquivo `skills/sinapse-consulta.md` define um comando `/consulta` que
funciona em todos os agentes suportados. A skill descreve o comando
equivalente em Python puro para agentes que não têm acesso ao MCP.

---

## 3. Fluxo de Escrita

O fluxo de escrita fecha o ciclo de memória: decisões e aprendizados
do agente são persistidos de volta ao vault, onde ficam disponíveis
para consultas futuras.

### Diagrama de Sequência

```
Agente      Plugin sinapse       Vault Obsidian       Graphify         claude-mem
  │                │                    │                 │                │
  │ memory_add     │                    │                 │                │
  │ ("decisão:     │                    │                 │                │
  │  migrar VPS")  │                    │                 │                │
  │───────────────►│                    │                 │                │
  │                │                    │                 │                │
  │                │ post_tool_use      │                 │                │
  │                │ detecta memory_add │                 │                │
  │                │                    │                 │                │
  │                │ _save_decision()   │                 │                │
  │                │───────────────────►│                 │                │
  │                │                    │                 │                │
  │                │ cria _decision/    │                 │                │
  │                │ 2026-05-21-        │                 │                │
  │                │ migrar-vps.md      │                 │                │
  │                │                    │                 │                │
  │                │ frontmatter YAML:  │                 │                │
  │                │ ─────────────────  │                 │                │
  │                │ tags: [decision]   │                 │                │
  │                │ status: active     │                 │                │
  │                │ created: 2026-05-21│                 │                │
  │                │ source: hermes     │                 │                │
  │                │───────────────────►│                 │                │
  │                │                    │                 │                │
  │                │ (se contém         │                 │                │
  │                │  learning signals) │                 │                │
  │                │ _save_learning()   │                 │                │
  │                │───────────────────►│                 │                │
  │                │                    │                 │                │
  │                │                    │  cron (6h)      │                │
  │                │                    │  reindexa       │                │
  │                │                    │────────────────►│                │
  │                │                    │                 │                │
  │                │                    │  reindexa       │                │
  │                │                    │◄────────────────│                │
  │                │                    │                 │                │
  │                │                    │ graph.json      │                │
  │                │                    │ atualizado      │                │
  │                │◄───────────────────│                 │                │
  │                │                    │                 │                │
  │ post_session   │                    │                 │                │
  │ _end           │                    │                 │                │
  │───────────────►│                    │                 │                │
  │                │                    │                 │                │
  │                │ _update_current    │                 │                │
  │                │ _state()           │                 │                │
  │                │───────────────────►│                 │                │
  │                │                    │                 │                │
  │                │ atualiza           │                 │                │
  │                │ _memory/           │                 │                │
  │                │ current-state.md   │                 │                │
  │                │ com WikiLinks      │                 │                │
  │                │ p/ decisões +      │                 │                │
  │                │ aprendizados       │                 │                │
  │                │                    │                 │                │
  │                │ (cron ou manual)   │                 │                │
  │                │ sync_claude_mem    │                 │                │
  │                │ _to_vault()        │                 │                │
  │                │──────────────────────────────────────────────────────►
  │                │                    │                 │                │
  │                │                    │                 │  observações   │
  │                │                    │                 │  exportadas    │
  │                │                    │                 │  p/ vault      │
  │                │◄─────────────────────────────────────────────────────
  │                │                    │                 │                │
```

### Formatos de Saída

**Decisão** (`cerebro/_decisions/YYYY-MM-DD-titulo.md`):
```yaml
---
tags: [decision]
status: active
created: 2026-05-21
updated: 2026-05-21
source: hermes-session
---

# Título da Decisão

Conteúdo completo da decisão registrada pelo agente.
```

**Aprendizado** (`cerebro/_learnings/YYYY-MM-DD-titulo.md`):
```yaml
---
tags: [learning]
status: active
created: 2026-05-21
updated: 2026-05-21
source: hermes-session
---

# Título do Aprendizado

Conteúdo do insight registrado.
```

**Estado atual** (`cerebro/_memory/current-state.md`):
```markdown
## Last Update: 2026-05-21 15:30

## Session: 2026-05-21 15:30

### Decisions
- Decisão: [[2026-05-21-migrar-vps]]
- Decisão: [[2026-05-21-estrategia-pricing]]

### Learnings
- Aprendizado: [[2026-05-21-padroes-system-prompts]]

### Summary
Resumo da sessão atual...
```

### Ciclo de Detecção de Aprendizados

O plugin detecta automaticamente quando uma observação contém um aprendizado
pelas palavras-chave:

```python
LEARNING_SIGNALS = ["aprendizado", "learning", "insight", "padrão",
                    "pattern", "lição"]
```

Quando uma dessas palavras aparece no conteúdo de um `memory_add`, o plugin
cria uma nota adicional em `_learnings/`.

### Sync Bidirecional (claude-mem → Vault)

A função `sync_claude_mem_to_vault()` no plugin consulta o SQLite do
claude-mem e exporta as últimas 10 observações como notas no vault:

```
SQL: SELECT id, content, created_at FROM observations
     ORDER BY created_at DESC LIMIT 10;
```

Este sync fecha o ciclo: o que foi registrado no claude-mem (camada
temporal) também aparece no vault Obsidian (fonte única de verdade).

---

## 4. Divisão de Responsabilidades

### Componentes e Donos

```
┌─────────────────────────────────────────────────────────────────────┐
│ COMPONENTE          │ RESPONSÁVEL POR                                │
├─────────────────────┼───────────────────────────────────────────────┤
│ cerebro/            │ Conteúdo do vault. Editado por humanos         │
│ (vault Obsidian)    │ no Obsidian E por agentes via plugin.          │
│                     │ Fonte única de verdade.                        │
├─────────────────────┼───────────────────────────────────────────────┤
│ graphify/           │ Indexação do vault → graph.json. Gerencia      │
│                     │ o conhecimento ESTRUTURAL (o QUE existe).      │
│                     │ Watch mode: reindexa automaticamente.          │
├─────────────────────┼───────────────────────────────────────────────┤
│ claude-mem/         │ Tracking de eventos de agentes. Gerencia       │
│                     │ a memória TEMPORAL (QUEM fez, QUANDO).         │
│                     │ Worker processa eventos em background.         │
├─────────────────────┼───────────────────────────────────────────────┤
│ rtk/                │ Otimização de comandos shell. Gerencia         │
│                     │ a camada de EXECUÇÃO (COMO otimizar).          │
│                     │ Hook pre_tool_call intercepta comandos.        │
├─────────────────────┼───────────────────────────────────────────────┤
│ plugins/hermes/     │ Plugin bidirecional: leitura (pre_prompt)      │
│                     │ + escrita (post_tool, post_session).           │
│                     │ Ponte entre Hermes e o vault.                  │
├─────────────────────┼───────────────────────────────────────────────┤
│ skills/             │ Skills multi-agente. Descrevem comandos        │
│                     │ como /consulta que funcionam em qualquer       │
│                     │ agente via MCP ou script standalone.           │
├─────────────────────┼───────────────────────────────────────────────┤
│ mcp/                │ Templates de configuração MCP. Copiados        │
│                     │ para ~/.hermes/mcp/ pelo install.sh.           │
├─────────────────────┼───────────────────────────────────────────────┤
│ scripts/            │ Scripts de automação: build, watch, MCP        │
│                     │ server, start workers.                         │
├─────────────────────┼───────────────────────────────────────────────┤
│ sinapse.yaml        │ Configuração central. Fonte de verdade         │
│                     │ para paths, portas, agentes suportados.        │
├─────────────────────┼───────────────────────────────────────────────┤
│ install.sh          │ Instalador universal. Detecta ambiente         │
│                     │ e configura tudo automaticamente.              │
├─────────────────────┼───────────────────────────────────────────────┤
│ cron/               │ Jobs periódicos: rebuild diário do grafo.      │
└─────────────────────┴───────────────────────────────────────────────┘
```

### Limites de Responsabilidade

- **O vault NÃO depende** de nenhuma camada para existir. Pode ser usado
  como um vault Obsidian normal sem Graphify, claude-mem ou RTK.

- **Graphify NÃO depende** de claude-mem ou RTK. Opera apenas sobre
  os arquivos do vault.

- **claude-mem NÃO depende** de Graphify ou RTK. Trackeia eventos
  de qualquer agente, em qualquer projeto.

- **RTK NÃO depende** de Graphify ou claude-mem. Opera como hook
  isolado no Hermes.

- **O plugin sinapse-memory** é o único componente que conhece
  todas as camadas: lê do Graphify e escreve no vault, com sync
  bidirecional do claude-mem.

---

## 5. Como Estender para Novos Agentes

### Passo a Passo

```
┌─────────────────────────────────────────────────────────────────────┐
│ 1. Adicionar no sinapse.yaml                                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│ agents:                                                             │
│   supported:                                                        │
│     - seu-agente          # ← adicionar aqui                        │
│   install_methods:                                                  │
│     seu-agente: "graphify install --platform seu-agente"            │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│ 2. Adicionar detector no install.sh                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│ declare -A AGENT_DETECTORS=(                                        │
│     ...                                                             │
│     ["seu-agente"]="seu-agente"                                     │
│ )                                                                    │
│                                                                     │
│ No case "$agent" in:                                                │
│     seu-agente)                                                     │
│         # Lógica específica de instalação                           │
│         cp "$PROJECT_ROOT/skills/sinapse-consulta.md" \             │
│            "$HOME/.seu-agente/skills/"                              │
│         ;;                                                          │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│ 3. Criar config MCP (se aplicável)                                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│ mcp/seu-agente.json:                                                │
│ {                                                                   │
│   "mcpServers": {                                                   │
│     "graphify": { ... },                                            │
│     "claude-mem": { ... }                                           │
│   }                                                                 │
│ }                                                                   │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│ 4. Adaptar skill existente (se necessário)                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│ Se o agente tem formato de skill diferente, crie uma variante       │
│ em skills/sinapse-consulta.<agente>.md                              │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Checklist de Integração

| Item | Descrição |
|------|-----------|
| ☐ sinapse.yaml | Agente listado em `agents.supported` |
| ☐ install.sh | Detector e lógica de instalação |
| ☐ MCP config | Template em `mcp/` (se usa MCP) |
| ☐ Skill | Skill de consulta adaptada (se usa skills) |
| ☐ Plugin | Plugin de memória (se suporta hooks como Hermes) |
| ☐ Teste | `./install.sh --force` instala o agente corretamente |

### Arquitetura de Plugins por Agente

```
Agente            Método de Conexão          Arquivo
────────────────  ───────────────────────    ──────────────────────────
Hermes            Plugin Python (hooks)      plugins/hermes/sinapse-memory.py
Claude Code       CLAUDE.md no vault + MCP   cerebro/CLAUDE.md
Codex             Plugin nativo + MCP        claude-mem/plugin/.codex-plugin/
OpenCode          AGENTS.md no projeto       cerebro/AGENTS.md
Cursor            Plugin claude-mem nativo   claude-mem/plugin/.claude-plugin/
Aider             MCP + graphify install     N/A (graphify gerencia)
Gemini CLI        MCP + graphify install     N/A (graphify gerencia)
Copilot           MCP + graphify install     N/A (graphify gerencia)
```

---

## 6. Como Adicionar Novo Projeto ao Vault

### Estrutura de um Projeto no Vault

```
cerebro/_projects/
└── nome-do-projeto/
    ├── README.md          ← overview do projeto
    ├── status.md          ← status atual (active, paused, completed)
    ├── decisions/         ← decisões específicas do projeto
    │   └── YYYY-MM-DD-titulo.md
    ├── learnings/         ← aprendizados do projeto
    │   └── YYYY-MM-DD-titulo.md
    └── notes/             ← notas técnicas, referências
        └── arquitetura.md
```

### Passo a Passo

```bash
# 1. Criar a pasta do projeto
mkdir -p cerebro/_projects/meu-projeto/{decisions,learnings,notes}

# 2. Criar README.md com frontmatter
cat > cerebro/_projects/meu-projeto/README.md << 'EOF'
---
tags: [project]
status: active
created: 2026-05-21
stack: [typescript, react, node]
repo: github.com/usuario/meu-projeto
---

# Meu Projeto

Descrição do projeto, objetivos, stack, etc.
EOF

# 3. Criar status.md
cat > cerebro/_projects/meu-projeto/status.md << 'EOF'
---
tags: [project, status]
updated: 2026-05-21
---

# Status: Meu Projeto

## Última atualização: 2026-05-21

- Fase atual: planejamento
- Próximo milestone: MVP
- Bloqueios: nenhum
EOF

# 4. Conectar ao knowledge graph existente
# Adicione WikiLinks no README.md para conectar com outros projetos:
echo "" >> cerebro/_projects/meu-projeto/README.md
echo "## Conexões" >> cerebro/_projects/meu-projeto/README.md
echo "- Relacionado a [[thoth]] (usa a mesma stack)" >> cerebro/_projects/meu-projeto/README.md
echo "- [[goals]] — alinhado com objetivo #2" >> cerebro/_projects/meu-projeto/README.md

# 5. Reindexar (se watch mode não estiver ativo)
./scripts/build-graph.sh
```

### Boas Práticas

1. **Sempre use frontmatter YAML** no topo de cada nota com pelo menos
   `tags`, `status` e `created`.

2. **Use WikiLinks** para conectar conceitos. O Graphify usa essas
   conexões para criar edges no knowledge graph.

3. **Mantenha o status atualizado.** Agentes consultam `status.md` para
   saber o contexto atual do projeto.

4. **Separe decisões por data.** Facilita a timeline e busca temporal.

5. **Conecte com `_knowledge/`.** Link para `[[goals]]`, `[[about-me]]`,
   etc., para dar contexto de negócio ao projeto.

---

## 7. Configuração do Obsidian

### Arquivos de Configuração

```
cerebro/.obsidian/
├── app.json              ← configurações do editor
├── appearance.json       ← tema e CSS
└── core-plugins.json     ← plugins nativos ativos
```

### Configurações Recomendadas

**app.json** (configurações ativas no vault):

```json
{
  "useMarkdownLinks": true,       // Usa [link](file.md) em vez de [[link]]
  "showHiddenFiles": true,        // Mostra arquivos ocultos (.claude/, .codex/, etc.)
  "showUnsupportedFiles": true,   // Mostra arquivos não-Markdown
  "showFrontmatter": true,        // Mostra YAML frontmatter no editor
  "livePreview": true,            // Preview em tempo real
  "defaultViewMode": "source",    // Abre em modo código fonte
  "newLinkFormat": "shortest",    // Caminho mais curto nos links
  "alwaysUpdateLinks": true,      // Atualiza links ao renomear
  "tabSize": 2                    // Indentação de 2 espaços
}
```

### Por que .obsidian/ existe no vault?

A pasta `.obsidian/` contém as configurações do Obsidian para este vault
específico. Isso garante que:

1. **Consistência entre máquinas** — mesma experiência de edição
2. **Formatação padronizada** — Markdown links, frontmatter visível
3. **Integridade de links** — atualização automática ao renomear
4. **Assets organizados** — anexos em `_attachments/`

> Nota: `.obsidian/` está no `.gitignore` do vault por padrão, pois
> configurações de UI podem variar entre usuários.

---

## 8. Cron e Automação

### Jobs Configurados

```
┌─────────────────────────────────────────────────────────────────────┐
│ CRON JOB                  │ SCHEDULE        │ AÇÃO                  │
├───────────────────────────┼─────────────────┼───────────────────────┤
│ build-graph.sh            │ 0 */6 * * *     │ Reindexa vault →      │
│ (via crontab)             │ (a cada 6h)     │ graph.json. Usa       │
│                           │                 │ cache SHA256 para     │
│                           │                 │ pular arquivos não    │
│                           │                 │ modificados.          │
├───────────────────────────┼─────────────────┼───────────────────────┤
│ sync-diario.sh            │ 0 2 * * 0       │ Rebuild COMPLETO do   │
│ (via cron/sync-diario.sh) │ (domingo 2am)   │ grafo com --force.    │
│                           │                 │ Ignora cache, reindexa│
│                           │                 │ tudo. Logs em logs/.  │
└───────────────────────────┴─────────────────┴───────────────────────┘
```

### Scripts de Automação

| Script | Função | Chamado por |
|--------|--------|-------------|
| `scripts/build-graph.sh` | Indexa vault → graph.json (sem LLM) | Cron (6h), manual |
| `scripts/serve-graph.sh` | Inicia MCP server Graphify | Cliente MCP (Hermes/Claude) |
| `scripts/start-claude-mem.sh` | Inicia worker claude-mem | MCP, systemd |
| `scripts/start-rtk.sh` | Configura plugin RTK no Hermes | install.sh, manual |
| `cron/sync-diario.sh` | Rebuild completo + log | Cron (semanal) |

### Logs

```
logs/
├── sync-20260521-020000.log
├── sync-20260520-020000.log
└── ...
```

Os logs de sync são rotacionados automaticamente: apenas os últimos 30
são mantidos.

### Cron (Principal)

```
Cron (a cada 6h):
  ✓ Sem dependência de terminal interativo
  ✓ Garante consistência mesmo offline
  ✓ Não consome recursos entre execuções
  ✓ Cobre mudanças feitas enquanto offline
  ✗ Latência de até 6h para novas mudanças (aceitável para vaults)

Watch Mode (--watch, NÃO recomendado):
  ✗ Requer terminal interativo (pty)
  ✗ Consome um processo contínuo
  ✗ Não sobrevive a reinicializações sem systemd/tmux
  ✓ Reindexa em segundos após mudança (se funcionar)
```

Recomendação: Use o cron. O watch mode do Graphify requer pty e é
incompatível com execução headless. Para reindexar manualmente a qualquer
momento: `./scripts/build-graph.sh`.

---

## 9. Troubleshooting

### Problemas Comuns e Soluções

```
┌─────────────────────────────────────────────────────────────────────┐
│ PROBLEMA                     │ CAUSA PROVÁVEL       │ SOLUÇÃO       │
├──────────────────────────────┼──────────────────────┼───────────────┤
│ Graphify não instala         │ uv/pipx não          │ curl -LsSf    │
│                              │ encontrado           │ https://astral│
│                              │                      │ .sh/uv/install│
│                              │                      │ .sh | sh      │
├──────────────────────────────┼──────────────────────┼───────────────┤
│ graph.json não gerado        │ Vault vazio ou       │ ./scripts/    │
│                              │ Graphify falhou      │ build-graph   │
│                              │ no parsing           │ .sh --force   │
├──────────────────────────────┼──────────────────────┼───────────────┤
│ MCP não conecta              │ Config não copiada   │ Verifique     │
│                              │ ou path errado       │ ~/.hermes/mcp/│
│                              │                      │ e reinicie o  │
│                              │                      │ Hermes        │
├──────────────────────────────┼──────────────────────┼───────────────┤
│ claude-mem worker parou      │ Processo morreu ou   │ cd claude-mem │
│                              │ porta em uso         │ && bun plugin/│
│                              │                      │ scripts/worker│
│                              │                      │ -service.cjs  │
│                              │                      │ start         │
├──────────────────────────────┼──────────────────────┼───────────────┤
│ RTK não otimiza comandos     │ Binário rtk não      │ pip install   │
│                              │ encontrado no PATH   │ rtk && ./    │
│                              │                      │ scripts/start-│
│                              │                      │ rtk.sh        │
├──────────────────────────────┼──────────────────────┼───────────────┤
│ Plugin sinapse não carrega   │ Arquivo não copiado  │ Verifique     │
│                              │ para ~/.hermes/      │ ~/.hermes/    │
│                              │ plugins/             │ plugins/      │
│                              │                      │ sinapse-memory│
│                              │                      │ /__init__.py  │
├──────────────────────────────┼──────────────────────┼───────────────┤
| Decisões não aparecem        | Cron ainda não       | ./scripts/    |
| no graph.json                | executou (6h)        | build-graph.sh |
|                              |                      | manual        |
├──────────────────────────────┼──────────────────────┼───────────────┤
| claude-mem não conecta       | Worker não iniciado  | cd claude-mem/|
|                              |                      | && npm run    |
|                              |                      | worker:start  |
├──────────────────────────────┼──────────────────────┼───────────────┤
| "No module named graphify"   | graphify não está    | pip install   |
|                              | no PATH do sistema   | -e graphify/  |
|                              |                      | [all]         |
└──────────────────────────────┴──────────────────────┴───────────────┘
```

### Verificação de Saúde

```bash
# Teste rápido de todas as camadas
cd ~/Documentos/Projects/sinapse_agent

# Camada 1: Graphify
python3 -c "import json; g=json.load(open('cerebro/graphify-out/graph.json')); print(f'Graphify OK: {len(g[\"nodes\"])} nodes, {len(g.get(\"links\",[]))} edges')"

# Camada 2: claude-mem
curl -s http://localhost:37700/health 2>/dev/null || echo "claude-mem worker offline"

# Camada 3: RTK
rtk --version 2>/dev/null || echo "RTK não instalado"

# Plugin Hermes
ls -la ~/.hermes/plugins/sinapse-memory/__init__.py 2>/dev/null || echo "Plugin sinapse não encontrado"
```

### Logs Úteis

```bash
# Logs do claude-mem
tail -f ~/Documentos/Projects/sinapse_agent/claude-mem/data/logs/claude-mem-$(date +%Y-%m-%d).log

# Logs de sync
ls -t ~/Documentos/Projects/sinapse_agent/logs/sync-*.log | head -1 | xargs cat

# Status do worker claude-mem
cd ~/Documentos/Projects/sinapse_agent/claude-mem && bun plugin/scripts/worker-service.cjs status
```

---

## 10. Referência de APIs

### Graphify MCP Tools

```
┌──────────────────────┬──────────────────────────────────────────────┐
│ Tool                 │ Assinatura / Descrição                       │
├──────────────────────┼──────────────────────────────────────────────┤
│ query_graph          │ query_graph(query: str) → List[Node]         │
│                      │ Busca semântica no grafo completo.           │
├──────────────────────┼──────────────────────────────────────────────┤
│ get_node             │ get_node(name: str) → Node                    │
│                      │ Detalhes de um nó específico (label, type,   │
│                      │ community, source_file, connections).        │
├──────────────────────┼──────────────────────────────────────────────┤
│ get_neighbors        │ get_neighbors(name: str) → List[Node]         │
│                      │ Todos os vizinhos diretos de um nó.          │
├──────────────────────┼──────────────────────────────────────────────┤
│ shortest_path        │ shortest_path(a: str, b: str) → List[str]     │
│                      │ Caminho mais curto entre dois conceitos.     │
└──────────────────────┴──────────────────────────────────────────────┘
```

### claude-mem MCP Tools

```
┌──────────────────────┬──────────────────────────────────────────────┐
│ Tool                 │ Assinatura / Descrição                       │
├──────────────────────┼──────────────────────────────────────────────┤
│ search               │ search(query: str, limit?: int) → List[Obs]  │
│                      │ Full-text search em observations (GIN index).│
├──────────────────────┼──────────────────────────────────────────────┤
│ timeline             │ timeline(anchor: ID, depth?: int) → List[Obs]│
│                      │ Contexto ao redor de uma observação.         │
├──────────────────────┼──────────────────────────────────────────────┤
│ get_observations     │ get_observations(ids: List[ID]) → List[Obs]  │
│                      │ Detalhes completos de observações específicas.│
├──────────────────────┼──────────────────────────────────────────────┤
│ smart_search         │ smart_search(query: str, path?: str) →       │
│                      │   List[Symbol]                                │
│                      │ Busca estrutural no código (tree-sitter AST).│
├──────────────────────┼──────────────────────────────────────────────┤
│ smart_outline        │ smart_outline(file_path: str) → Outline       │
│                      │ Estrutura de símbolos de um arquivo.         │
├──────────────────────┼──────────────────────────────────────────────┤
│ build_corpus         │ build_corpus(name: str, filters...) → Corpus │
│                      │ Cria corpus de conhecimento filtrado.        │
├──────────────────────┼──────────────────────────────────────────────┤
│ query_corpus         │ query_corpus(name: str, question: str) → R   │
│                      │ Pergunta a um corpus primed com LLM.         │
├──────────────────────┼──────────────────────────────────────────────┤
│ prime_corpus         │ prime_corpus(name: str) → Session             │
│                      │ Inicia sessão AI com conhecimento do corpus. │
└──────────────────────┴──────────────────────────────────────────────┘
```

### Plugin sinapse-memory (Hermes)

```python
# Hooks registrados
def register(ctx):
    ctx.register_hook("pre_prompt_build", _pre_prompt_build)
    ctx.register_hook("post_tool_use", _post_tool_use)
    ctx.register_hook("post_session_end", _post_session_end)

# Constantes
MAX_CONTEXT_CHARS = 3000   # limite de contexto injetado
MAX_NODES = 5               # máximo de nodes na resposta

# Ferramentas detectadas para escrita
DECISION_TOOLS = {"memory_add", "observation_add",
                  "mcp_claude_mem_memory_add"}

# Sinais de aprendizado
LEARNING_SIGNALS = ["aprendizado", "learning", "insight",
                    "padrão", "pattern", "lição"]
```

### sinapse.yaml (Schema)

```yaml
project:
  name: str              # Nome do projeto
  version: str           # Versão semântica
  description: str       # Descrição

vault:
  path: str              # Caminho relativo do vault
  format: "obsidian"     # Formato do vault
  language: str          # Idioma (pt-BR, en, etc.)
  indexer: "graphify"    # Ferramenta de indexação
  watch: bool            # Reindexar automaticamente

graphify:
  package: "graphifyy"   # Nome do pacote PyPI
  install_method: str    # uv | pipx | pip
  extras: [str]          # Extras: all, pdf, office, mcp, neo4j, ollama
  output_dir: str        # Diretório de output
  mcp_port: int          # 0 = stdio, N = porta HTTP
  watch: bool            # Flag --watch
  obsidian_export: bool   # Flag --obsidian
  global_graph: bool      # Flag --global

claude_mem:
  port: int              # Porta do worker
  install_method: "npx"  # Método de instalação
  worker_autostart: bool  # Auto-iniciar worker

rtk:
  plugin_dir: str        # Diretório do plugin no projeto
  install_path: str      # Destino no Hermes

agents:
  supported: [str]       # Lista de agentes suportados
  install_methods:       # Comandos graphify install por agente
    agente: str

mcp_servers:
  <nome>:
    command: str         # Comando para iniciar
    transport: "stdio"   # stdio | http
    port: int            # Porta (se http)
    enabled: bool

cron:
  sync_schedule: str     # Cron expression (reindex)
  rebuild_schedule: str  # Cron expression (rebuild completo)
```

---

## Diagrama de Estados do Sistema

```
                    ┌──────────┐
                    │  OFFLINE │
                    └────┬─────┘
                         │ ./install.sh
                         ▼
              ┌─────────────────────┐
              │    INSTALANDO       │
              │                     │
              │ 1. Deps check       │
              │ 2. Graphify install │
              │ 3. Agent skills     │──── erro ────► ┌──────────┐
              │ 4. claude-mem       │                │  ERRO    │
              │ 5. RTK              │                │  (log +  │
              │ 6. MCP configs      │                │   exit)  │
              │ 7. Cron             │                └──────────┘
              └──────────┬──────────┘
                         │ sucesso
                         ▼
              ┌─────────────────────┐
              │      ATIVO         │
              │                     │
              │ ┌─────────────────┐ │
              │ │ Watch mode      │ │── arquivo modificado ──► reindexa
              │ │ (opcional)      │ │
              │ └─────────────────┘ │
              │ ┌─────────────────┐ │
              │ │ Cron (c/6h)     │ │── schedule ──► build-graph.sh
              │ └─────────────────┘ │
              │ ┌─────────────────┐ │
              │ │ Cron (dom 2am)  │ │── schedule ──► sync-diario.sh
              │ └─────────────────┘ │
              │ ┌─────────────────┐ │
              │ │ MCP servers     │ │── agente conecta ──► query/write
              │ └─────────────────┘ │
              │ ┌─────────────────┐ │
              │ │ Plugin Hermes   │ │── pre_prompt ──► injeta contexto
              │ │                 │ │── post_tool ──► salva decisão
              │ │                 │ │── post_session─► atualiza estado
              │ └─────────────────┘ │
              │ ┌─────────────────┐ │
              │ │ RTK hook        │ │── pre_tool_call──► otimiza cmd
              │ └─────────────────┘ │
              └─────────────────────┘
```

---

Fim do ARCHITECTURE.md. Para qualquer dúvida, consulte o `sinapse.yaml`
ou o código-fonte do plugin em `plugins/hermes/sinapse-memory.py`.
